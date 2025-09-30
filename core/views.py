from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, FileResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.apps import apps
import json
import logging
import os
import tempfile
from datetime import datetime, date, timedelta

from .models import Contract, PaymentMilestone, PaymentTerms, ContractClarification, ContractType, HubSpotDeal, HubSpotDealMatch
from .services.contract_processor import ContractProcessor, ContractProcessingError
from .services.excel_exporter import ExcelExporter
from django.db import models
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def home(request):
    """Home page view."""
    context = {
        'total_contracts': Contract.objects.count(),
        'active_contracts': Contract.objects.filter(status='completed').count(),
        'pending_payments': PaymentMilestone.objects.filter(status='pending').count(),
        'overdue_payments': PaymentMilestone.objects.filter(status='overdue').count(),
    }
    return render(request, 'core/home.html', context)


def _get_contract_summary():
    """Aggregate contract summary metrics for dashboards and APIs."""
    contracts_queryset = Contract.objects.all()
    today = timezone.now().date()
    month_start = today.replace(day=1)

    return {
        'total_contracts': contracts_queryset.count(),
        'needs_clarification': contracts_queryset.filter(status='needs_clarification').count(),
        'total_value': contracts_queryset.aggregate(total=Sum('total_value'))['total'] or 0,
        'completed_this_month': contracts_queryset.filter(
            status='completed',
            last_modified__date__gte=month_start,
            last_modified__date__lte=today
        ).count(),
    }


def contract_list(request):
    """List all contracts."""
    contracts_queryset = Contract.objects.all()

    status_filter = request.GET.get('status', 'all')
    status_map = {
        'needs_review': 'needs_clarification',
        'completed': 'completed',
        'processing': 'processing',
    }

    if status_filter in status_map:
        contracts = contracts_queryset.filter(status=status_map[status_filter])
    else:
        contracts = contracts_queryset
        status_filter = 'all'

    # Search functionality  
    search_query = request.GET.get('search', '')
    if search_query:
        from django.db.models import Q
        
        # Use icontains for partial case-insensitive matching
        contracts = contracts.filter(
            Q(client_name__icontains=search_query) |
            Q(contract_name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    summary = _get_contract_summary()

    context = {
        'contracts': contracts,
        'summary': summary,
        'active_filter': status_filter,
        'search_query': search_query,  # Add this line
    }
    return render(request, 'core/contract_list.html', context)


def contract_metrics(request):
    """Return contract summary metrics as JSON."""
    summary = _get_contract_summary()
    response = summary.copy()
    total_value = response.get('total_value') or 0
    response['total_value'] = float(total_value)
    return JsonResponse(response)


def contract_detail(request, contract_id):
    """Detail view for a specific contract."""
    contract = get_object_or_404(Contract, id=contract_id)
    payment_milestones = contract.payment_milestones.all().order_by('due_date')
    clarifications = contract.clarifications.all().order_by('-created_at')  # ADD THIS
    
    # Count answered clarifications for the Apply button
    answered_count = clarifications.filter(answered=True).count()
    unanswered_count = clarifications.filter(answered=False).count()
    
    # Get and validate the 'next' parameter
    next_url = request.GET.get('next', '')
    if next_url:
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse('core:contract_list')
    else:
        next_url = reverse('core:contract_list')
    
    context = {
        'contract': contract,
        'payment_milestones': payment_milestones,
        'payment_terms': getattr(contract, 'payment_terms', None),
        'clarifications': clarifications,  # ADD THIS
        'answered_count': answered_count,
        'unanswered_count': unanswered_count,
        'back_url': next_url,
        'contract_types': ContractType.objects.filter(is_active=True),
        'status_choices': [
            ('needs_clarification', 'Needs Review'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
        ],
        'payment_method_choices': PaymentTerms.PAYMENT_METHOD_CHOICES,
        'payment_frequency_choices': PaymentTerms.PAYMENT_FREQUENCY_CHOICES,
    }
    return render(request, 'core/contract_detail.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def upload_contract(request):
    """Handle contract PDF upload and processing."""
    try:
        # Check if file was uploaded
        if 'pdf_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No PDF file provided'
            }, status=400)
        
        pdf_file = request.FILES['pdf_file']
        
        # Validate file type
        if not pdf_file.name.lower().endswith('.pdf'):
            return JsonResponse({
                'success': False,
                'error': 'File must be a PDF'
            }, status=400)
        
        # Validate file size (10MB limit)
        max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 10 * 1024 * 1024)
        if pdf_file.size > max_size:
            return JsonResponse({
                'success': False,
                'error': f'File too large. Maximum size: {max_size / (1024*1024):.1f}MB'
            }, status=400)
        
        # Process the contract
        processor = ContractProcessor()
        result = processor.process_contract(pdf_file, user=request.user if request.user.is_authenticated else None)
        
        if result['success']:
            return JsonResponse({
                'success': True,
                'contract_id': result['contract_id'],
                'confidence_score': float(result['confidence_score']),
                'extraction_method': result['extraction_method'],
                'payment_milestones_created': result['payment_milestones_created'],
                'warnings': result.get('warnings', []),
                'message': f"Contract processed successfully with {result['confidence_score']:.1f}% confidence"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown processing error')
            }, status=500)
            
    except Exception as e:
        logger.error(f"Upload contract error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Upload failed: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def upload_status(request, contract_id):
    """Get upload/processing status for a contract."""
    try:
        contract = get_object_or_404(Contract, id=contract_id)
        
        return JsonResponse({
            'contract_id': contract.id,
            'status': contract.status,
            'confidence_score': float(contract.confidence_score) if contract.confidence_score else 0.0,
            'extraction_method': contract.extraction_method,
            'payment_milestones_count': contract.payment_milestones.count(),
            'upload_date': contract.upload_date.isoformat(),
            'contract_url': f'/contracts/{contract.id}/'
        })
        
    except Exception as e:
        logger.error(f"Upload status error: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


def test_results(request):
    """Display batch test results from /2025 folder processing"""
    try:
        # Get all contracts that were processed from the 2025 folder
        contracts = Contract.objects.filter(
            pdf_file__icontains='2025'
        ).order_by('-upload_date')
        
        # Calculate statistics
        total_contracts = contracts.count()
        
        if total_contracts > 0:
            # Confidence distribution
            high_confidence = contracts.filter(confidence_score__gte=85).count()
            medium_confidence = contracts.filter(
                confidence_score__gte=60, 
                confidence_score__lt=85
            ).count()
            low_confidence = contracts.filter(confidence_score__lt=60).count()
            ai_assistance_needed = contracts.filter(confidence_score__lt=85).count()
            
            # Calculate averages
            avg_confidence = contracts.aggregate(
                avg_confidence=models.Avg('confidence_score')
            )['avg_confidence'] or 0
            
            # Contracts needing manual review
            manual_review_contracts = contracts.filter(
                confidence_score__lt=85
            ).order_by('confidence_score')[:10]
            
            # Recent processing activity
            recent_contracts = contracts[:10]
            
            # Error analysis
            error_patterns = {}
            for contract in contracts.filter(confidence_score__lt=60):
                raw_data = contract.raw_extracted_data
                if raw_data and 'extraction_warnings' in raw_data:
                    for warning in raw_data['extraction_warnings']:
                        error_patterns[warning] = error_patterns.get(warning, 0) + 1
            
        else:
            high_confidence = medium_confidence = low_confidence = ai_assistance_needed = 0
            avg_confidence = 0
            manual_review_contracts = recent_contracts = []
            error_patterns = {}
        
        context = {
            'total_contracts': total_contracts,
            'high_confidence': high_confidence,
            'medium_confidence': medium_confidence,
            'low_confidence': low_confidence,
            'ai_assistance_needed': ai_assistance_needed,
            'avg_confidence': avg_confidence,
            'manual_review_contracts': manual_review_contracts,
            'recent_contracts': recent_contracts,
            'error_patterns': error_patterns,
            'success_rate': (total_contracts - low_confidence) / total_contracts * 100 if total_contracts > 0 else 0
        }
        
        return render(request, 'core/test_results.html', context)
        
    except Exception as e:
        logger.error(f"Test results view error: {str(e)}")
        return render(request, 'core/test_results.html', {
            'error': str(e),
            'total_contracts': 0
        })


def export_excel(request):
    """Export contracts to Excel format."""
    try:
        logger.info("Starting Excel export")
        
        # Get filter parameters from request
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        status_filter = request.GET.get('status')
        
        logger.info(f"Export filters - date_from: {date_from}, date_to: {date_to}, status: {status_filter}")
        
        # Build queryset with filters
        contracts = Contract.objects.all()
        logger.info(f"Initial contracts count: {contracts.count()}")
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                contracts = contracts.filter(upload_date__date__gte=date_from_obj)
                logger.info(f"After date_from filter: {contracts.count()} contracts")
            except ValueError as e:
                logger.warning(f"Invalid date_from format: {date_from}, error: {e}")
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                contracts = contracts.filter(upload_date__date__lte=date_to_obj)
                logger.info(f"After date_to filter: {contracts.count()} contracts")
            except ValueError as e:
                logger.warning(f"Invalid date_to format: {date_to}, error: {e}")
                pass
        
        if status_filter:
            contracts = contracts.filter(status=status_filter)
            logger.info(f"After status filter: {contracts.count()} contracts")
        
        # Order by upload date (most recent first)
        contracts = contracts.order_by('-upload_date')
        
        # Check if there are contracts to export
        if not contracts.exists():
            logger.warning("No contracts found matching the criteria")
            return JsonResponse({
                'success': False,
                'error': 'No contracts found matching the criteria'
            }, status=404)
        
        logger.info(f"Final contracts count for export: {contracts.count()}")
        
        # Create temporary file for Excel export
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        temp_file.close()
        logger.info(f"Created temporary file: {temp_file.name}")
        
        # Export to Excel
        logger.info("Starting Excel export process")
        exporter = ExcelExporter()
        excel_file_path = exporter.export_contracts_to_excel(contracts, temp_file.name)
        logger.info(f"Excel export completed, file saved to: {excel_file_path}")
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contracts_export_{timestamp}.xlsx"
        
        # Return file as download
        logger.info(f"Preparing file response for: {filename}")
        response = FileResponse(
            open(excel_file_path, 'rb'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Clean up temporary file after response
        def cleanup_temp_file():
            try:
                os.unlink(excel_file_path)
                logger.info(f"Cleaned up temporary file: {excel_file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temporary file: {e}")
        
        # Remove the problematic Connection header that was causing the 500 error
        # response['Connection'] = 'close'  # This was causing the hop-by-hop header error
        response.closed = cleanup_temp_file
        
        logger.info(f"Excel export completed successfully: {filename} with {contracts.count()} contracts")
        return response
        
    except Exception as e:
        logger.error(f"Excel export failed: {str(e)}", exc_info=True)
        return HttpResponse(f"Export failed: {str(e)}", status=500)


def check_contracts(request):
    """Diagnostic view to check database state."""
    contracts = Contract.objects.all()
    return JsonResponse({
        'count': contracts.count(),
        'contracts': list(contracts.values('id', 'contract_name', 'status')[:5])
    })


@require_http_methods(["POST"])
def delete_contract(request, contract_id):
    """Delete a contract and all its related data."""
    try:
        # Get the contract
        contract = get_object_or_404(Contract, id=contract_id)
        
        # Store contract info for success message
        contract_name = contract.contract_name
        client_name = contract.client_name
        
        # Delete the contract (this will cascade delete payment milestones and terms)
        contract.delete()
        
        # Add success message
        messages.success(
            request, 
            f'Contract "{contract_name}" for client "{client_name}" has been successfully deleted.'
        )
        
        logger.info(f"Contract {contract_id} ({contract_name}) deleted by user")
        
        # Redirect back to contract list
        return redirect('core:contract_list')
        
    except Exception as e:
        logger.error(f"Delete contract error: {str(e)}")
        messages.error(
            request, 
            f'Failed to delete contract: {str(e)}'
        )
        return redirect('core:contract_list')


@require_http_methods(["POST"])
def answer_clarification(request, clarification_id):
    """Save user's answer to a clarification question."""
    try:
        clarification = get_object_or_404(ContractClarification, id=clarification_id)
        
        # Get the answer from POST data
        answer = request.POST.get('answer', '').strip()
        
        if not answer:
            messages.error(request, 'Please provide an answer before submitting.')
            # Stay on the contract detail page after validation failure
            return redirect('core:contract_detail', contract_id=clarification.contract.id)
        
        # Mark the clarification as answered
        clarification.mark_as_answered(answer)
        
        # Success message
        messages.success(
            request,
            f'Answer saved for "{clarification.field_name}" on contract "{clarification.contract.contract_name}"'
        )
        
        logger.info(f"Clarification {clarification_id} answered for contract {clarification.contract.id}")
        
        # Check if there are more clarifications for this contract
        remaining = ContractClarification.objects.filter(
            contract=clarification.contract,
            answered=False
        ).count()
        
        if remaining == 0:
            # All clarifications answered - apply them to the contract
            contract = clarification.contract
            if contract.status == 'needs_clarification':
                # Apply clarifications to update contract fields
                updates_made = contract.apply_clarifications()
                
                # Update status to completed
                contract.status = 'completed'
                contract.save()
                
                if updates_made:
                    updates_summary = ', '.join(updates_made[:3])  # Show first 3 updates
                    if len(updates_made) > 3:
                        updates_summary += f' and {len(updates_made) - 3} more'
                    
                    messages.success(
                        request,
                        f'✅ All clarifications applied! Contract "{contract.contract_name}" updated: {updates_summary}'
                    )
                else:
                    messages.info(
                        request,
                        f'All clarifications answered for contract "{contract.contract_name}". Status updated to completed.'
                    )
        
    except Exception as e:
        logger.error(f"Error answering clarification {clarification_id}: {str(e)}")
        messages.error(request, f'Failed to save answer: {str(e)}')
    
    # Stay on the contract detail page after answering
    return redirect('core:contract_detail', contract_id=clarification.contract.id)


@require_http_methods(["POST"])
def apply_contract_clarifications(request, contract_id):
    """Manually apply all answered clarifications to a contract."""
    try:
        contract = get_object_or_404(Contract, id=contract_id)
        
        # Check if there are any answered clarifications to apply
        answered_clarifs = contract.clarifications.filter(answered=True)
        unanswered = contract.clarifications.filter(answered=False).count()
        
        if not answered_clarifs.exists():
            messages.warning(
                request,
                'No answered clarifications to apply.'
            )
            return redirect('core:contract_detail', contract_id=contract.id)
        
        # Apply clarifications
        updates_made = contract.apply_clarifications()
        
        # Update status if all clarifications are answered
        if unanswered == 0 and contract.status == 'needs_clarification':
            contract.status = 'completed'
            contract.save()
            status_message = " Contract status updated to completed."
        else:
            status_message = f" {unanswered} clarification(s) still pending."
        
        if updates_made:
            updates_summary = ', '.join(updates_made[:5])  # Show first 5 updates
            if len(updates_made) > 5:
                updates_summary += f' and {len(updates_made) - 5} more'
            
            messages.success(
                request,
                f'✅ Successfully applied clarifications: {updates_summary}.{status_message}'
            )
        else:
            messages.info(
                request,
                f'No updates were made to the contract.{status_message}'
            )
        
        logger.info(f"Manually applied clarifications for contract {contract_id}")
        
    except Exception as e:
        logger.error(f"Error applying clarifications for contract {contract_id}: {str(e)}")
        messages.error(request, f'Failed to apply clarifications: {str(e)}')
    
    # Stay on the contract detail page after applying
    return redirect('core:contract_detail', contract_id=contract.id)


def generate_invoice_schedule(contract, start_date, end_date):
    """Generate recurring invoice schedule for a contract."""
    from datetime import datetime, timedelta
    
    invoices = []
    
    # Handle different frequencies
    if hasattr(contract, 'payment_terms') and contract.payment_terms:
        if contract.payment_terms.payment_frequency == 'monthly':
            current = contract.start_date
            while current <= end_date and current <= contract.end_date:
                invoices.append({
                    'date': current,
                    'amount': contract.total_value / 12 if contract.total_value else 0,
                    'type': 'monthly',
                    'contract_id': contract.id,
                    'contract_number': contract.contract_number,
                    'client': contract.client_name or 'Unknown'
                })
                # Add 30 days for next month (simplified)
                current = current + timedelta(days=30)
                
        elif contract.payment_terms.payment_frequency == 'quarterly':
            current = contract.start_date
            while current <= end_date and current <= contract.end_date:
                invoices.append({
                    'date': current,
                    'amount': contract.total_value / 4 if contract.total_value else 0,
                    'type': 'quarterly',
                    'contract_id': contract.id,
                    'contract_number': contract.contract_number,
                    'client': contract.client_name or 'Unknown'
                })
                # Add 90 days for next quarter (simplified)
                current = current + timedelta(days=90)
                
        elif contract.payment_terms.payment_frequency == 'annually':
            current = contract.start_date
            while current <= end_date and current <= contract.end_date:
                invoices.append({
                    'date': current,
                    'amount': contract.total_value if contract.total_value else 0,
                    'type': 'annually',
                    'contract_id': contract.id,
                    'contract_number': contract.contract_number,
                    'client': contract.client_name or 'Unknown'
                })
                # Add 365 days for next year (simplified)
                current = current + timedelta(days=365)
    
    # Add payment milestones
    for milestone in contract.payment_milestones.all():
        if milestone.due_date <= end_date and milestone.due_date >= start_date:
            invoices.append({
                'date': milestone.due_date,
                'amount': milestone.amount,
                'type': 'milestone',
                'contract_id': contract.id,
                'contract_number': contract.contract_number,
                'client': contract.client_name or 'Unknown'
            })
    
    return invoices


def forecast_view(request):
    """View for payment forecast dashboard."""
    from datetime import datetime, timedelta
    
    # Get active tab from request
    active_tab = request.GET.get('tab', 'table')
    
    # Get today's date first
    today = datetime.now().date()
    
    # Check for custom date range
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')
    
    if custom_start and custom_end:
        start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
    else:
        # Default logic for preset ranges
        days = request.GET.get('days', '30')
        if days == 'custom':
            # Show last year by default for custom
            start_date = today - timedelta(days=365)
            end_date = today + timedelta(days=365)
        else:
            # Existing logic
            try:
                days_int = int(days) if days != 'all' else 365
            except ValueError:
                days_int = 30
            start_date = today
            end_date = today + timedelta(days=days_int)
    
    # Get sort parameters
    sort_by = request.GET.get('sort', 'due_date')
    sort_order = request.GET.get('order', 'asc')
    
    # Get active contracts
    contracts = Contract.objects.filter(
        status__in=['active', 'needs_clarification']
    ).select_related('payment_terms')
    
    # Calculate upcoming payments for specified date range
    upcoming_payments = []
    timeline_invoices = []
    
    for contract in contracts:
        # Generate invoice schedule for timeline view
        contract_invoices = generate_invoice_schedule(contract, start_date, end_date)
        timeline_invoices.extend(contract_invoices)
        
        # For Table View, generate all payments in date range
        if contract.total_value and contract.total_value > 0:
            # Use same logic as Timeline - generate ALL payments in range
            if hasattr(contract, 'payment_terms') and contract.payment_terms.payment_frequency == 'monthly':
                current_date = max(contract.start_date, start_date) if contract.start_date else start_date
                
                while current_date <= end_date:
                    if contract.end_date and current_date > contract.end_date:
                        break
                        
                    upcoming_payments.append({
                        'client': contract.client_name or 'Unknown',
                        'amount': contract.total_value / 12,
                        'due_date': current_date,
                        'contract_number': contract.contract_number,
                        'frequency': 'Monthly',
                        'contract_id': contract.id
                    })
                    
                    # Move to next month
                    if current_date.month == 12:
                        current_date = current_date.replace(year=current_date.year + 1, month=1)
                    else:
                        current_date = current_date.replace(month=current_date.month + 1)
    
    # Sort payments by date for Table View
    upcoming_payments.sort(key=lambda x: (x['due_date'], x['client']))
    
    # Apply user-specified sorting if different from default
    if upcoming_payments:
        reverse = (sort_order == 'desc')
        if sort_by == 'client':
            upcoming_payments.sort(key=lambda x: x['client'], reverse=reverse)
        elif sort_by == 'amount':
            upcoming_payments.sort(key=lambda x: x['amount'] or 0, reverse=reverse)
        elif sort_by == 'due_date':
            upcoming_payments.sort(key=lambda x: x['due_date'], reverse=reverse)
    
    # Sort timeline invoices by date
    timeline_invoices.sort(key=lambda x: x['date'])
    
    # Group invoices by client and prepare months
    from collections import defaultdict
    timeline_by_client = defaultdict(list)
    
    for invoice in timeline_invoices:
        timeline_by_client[invoice['client']].append(invoice)
    
    # Calculate months span for timeline
    months_diff = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
    
    # Generate list of months for columns based on actual date range
    timeline_months = []
    current_month = start_date.replace(day=1)
    for i in range(months_diff + 1):
        timeline_months.append(current_month)
        # Move to next month
        if current_month.month == 12:
            current_month = current_month.replace(year=current_month.year + 1, month=1)
        else:
            current_month = current_month.replace(month=current_month.month + 1)
    
    # Prepare calendar view data
    import calendar
    from collections import defaultdict
    
    # Get calendar month from request or use start_date
    cal_month_param = request.GET.get('cal_month')
    if cal_month_param:
        cal_date = datetime.strptime(cal_month_param, '%Y-%m').date()
        cal_month = cal_date.month
        cal_year = cal_date.year
    else:
        cal_month = start_date.month
        cal_year = start_date.year
    
    # Group invoices by date for calendar
    invoices_by_date = defaultdict(list)
    for invoice in timeline_invoices:
        if invoice['date'].month == cal_month and invoice['date'].year == cal_year:
            invoices_by_date[invoice['date'].day].append(invoice)
    
    # Create calendar grid
    cal = calendar.monthcalendar(cal_year, cal_month)
    calendar_days = []
    
    for week in cal:
        for day in week:
            if day == 0:  # Empty cell
                calendar_days.append({'date': None, 'invoices': []})
            else:
                day_date = datetime(cal_year, cal_month, day).date()
                calendar_days.append({
                    'date': day_date,
                    'invoices': invoices_by_date.get(day, [])
                })
    
    # Calculate metrics
    total_monthly = sum(p['amount'] for p in upcoming_payments if p['amount'])
    payments_count = len(upcoming_payments)
    average_invoice = total_monthly / payments_count if payments_count > 0 else 0

    context = {
        'active_tab': active_tab,
        'upcoming_payments': upcoming_payments,
        'timeline_invoices': timeline_invoices,
        'timeline_by_client': dict(timeline_by_client),
        'timeline_months': timeline_months,
        'calendar_days': calendar_days,
        'calendar_month': datetime(cal_year, cal_month, 1).date(),
        'total_monthly': total_monthly,
        'payments_count': payments_count,
        'average_invoice': average_invoice,
        'sort_by': sort_by,
        'sort_order': sort_order,
    }
    return render(request, 'core/forecast.html', context)


def export_forecast(request):
    """Export forecast data to Excel."""
    from openpyxl import Workbook
    from django.http import HttpResponse
    from datetime import datetime, timedelta
    
    # Get same parameters as forecast view
    today = datetime.now().date()
    
    # Check for custom date range
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')
    
    if custom_start and custom_end:
        start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
        end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
    else:
        # Default logic for preset ranges
        days = request.GET.get('days', '30')
        if days == 'custom':
            # Show last year by default for custom
            start_date = today - timedelta(days=365)
            end_date = today + timedelta(days=365)
        else:
            # Existing logic
            try:
                days_int = int(days) if days != 'all' else 365
            except ValueError:
                days_int = 30
            start_date = today
            end_date = today + timedelta(days=days_int)
    
    # Get contracts and calculate payments (same logic as forecast_view)
    contracts = Contract.objects.filter(
        status__in=['active', 'needs_clarification']
    ).select_related('payment_terms')
    
    upcoming_payments = []
    for contract in contracts:
        if hasattr(contract, 'payment_terms'):
            # Simple calculation for monthly payments
            if contract.payment_terms.payment_frequency == 'monthly':
                upcoming_payments.append({
                    'client': contract.client_name or 'Unknown',
                    'contract': contract.contract_number,
                    'amount': float(contract.total_value / 12) if contract.total_value else 0,
                    'frequency': 'Monthly',
                    'due_date': end_date
                })
    
    # Create Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Payment Forecast"
    
    # Headers
    headers = ['Client', 'Contract', 'Amount', 'Frequency', 'Due Date']
    ws.append(headers)
    
    # Data
    for payment in upcoming_payments:
        ws.append([
            payment['client'],
            payment['contract'],
            payment['amount'],
            payment['frequency'],
            payment['due_date'].strftime('%Y-%m-%d')
        ])
    
    # Response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="forecast_{today}.xlsx"'
    wb.save(response)
    return response


@require_http_methods(["POST"])
def update_po_info(request, contract_id):
    """Update PO Number and Budget for a contract via AJAX"""
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    contract.po_number = data.get('po_number') or None
    contract.po_budget = data.get('po_budget') or None
    contract.save()
    
    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def update_contract_type(request, contract_id):
    """Update the contract type selection via AJAX."""
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)

    contract_type_id = data.get('contract_type')

    if contract_type_id:
        try:
            contract_type = ContractType.objects.get(id=contract_type_id, is_active=True)
            contract.contract_type = contract_type
        except ContractType.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid contract type'}, status=400)
    else:
        contract.contract_type = None

    contract.save(update_fields=['contract_type'])

    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def update_contract_status(request, contract_id):
    """Update contract status via AJAX"""
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    new_status = data.get('status')
    
    # Validate status - only allow these three
    valid_statuses = ['needs_clarification', 'processing', 'completed']
    if new_status not in valid_statuses:
        return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
    
    contract.status = new_status
    contract.save()
    
    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def update_contract_dates(request, contract_id):
    """Update contract start and end dates via AJAX"""
    from datetime import datetime
    
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')
    
    try:
        # Parse start_date
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = None
        
        # Parse end_date (allow empty for ongoing contracts)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = None
        
        # Validate: start_date <= end_date (if both exist)
        if start_date and end_date and start_date > end_date:
            return JsonResponse({
                'success': False, 
                'error': 'Start date must be before end date'
            }, status=400)
        
        # Update contract
        contract.start_date = start_date
        contract.end_date = end_date
        contract.save()
        
        return JsonResponse({'success': True})
        
    except ValueError:
        return JsonResponse({
            'success': False, 
            'error': 'Invalid date format'
        }, status=400)


@require_http_methods(["POST"])
def update_payment_terms(request, contract_id):
    """Update or create payment terms via AJAX"""
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    payment_method = data.get('payment_method')
    payment_frequency = data.get('payment_frequency')
    
    # Validate choices
    from core.models import PaymentTerms
    valid_methods = [choice[0] for choice in PaymentTerms.PAYMENT_METHOD_CHOICES]
    valid_frequencies = [choice[0] for choice in PaymentTerms.PAYMENT_FREQUENCY_CHOICES]
    
    if payment_method not in valid_methods:
        return JsonResponse({'success': False, 'error': 'Invalid payment method'}, status=400)
    if payment_frequency not in valid_frequencies:
        return JsonResponse({'success': False, 'error': 'Invalid payment frequency'}, status=400)
    
    # Create or update PaymentTerms
    payment_terms, created = PaymentTerms.objects.get_or_create(
        contract=contract,
        defaults={
            'payment_method': payment_method,
            'payment_frequency': payment_frequency,
            'grace_period_days': 0
        }
    )
    
    if not created:
        # Warn about frequency change impact
        old_frequency = payment_terms.payment_frequency
        if old_frequency != payment_frequency:
            # Log or track frequency change if needed
            pass
            
        payment_terms.payment_method = payment_method
        payment_terms.payment_frequency = payment_frequency
        payment_terms.save()
    
    return JsonResponse({'success': True, 'created': created})


@require_http_methods(["POST"])
def update_milestone(request, contract_id):
    """Update milestone information for a contract via AJAX"""
    from .models import PaymentMilestone
    from datetime import datetime
    
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    try:
        milestone_id = data.get('milestone_id')
        milestone = get_object_or_404(PaymentMilestone, id=milestone_id, contract=contract)
        
        # Handle generic field updates
        field = data.get('field')
        value = data.get('value')
        
        if field and value is not None:
            if field == 'invoice_date':
                try:
                    milestone.invoice_date = datetime.strptime(value, '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid invoice date format'})
            elif field == 'due_date':
                try:
                    milestone.due_date = datetime.strptime(value, '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid due date format'})
            elif field == 'amount':
                try:
                    milestone.amount = float(value)
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid amount format'})
            elif field == 'milestone_name':
                milestone.milestone_name = value
            elif field == 'payment_reference':
                milestone.payment_reference = value
            else:
                return JsonResponse({'success': False, 'error': f'Unknown field: {field}'})
        
        # Legacy support for direct field updates
        milestone.milestone_name = data.get('milestone_name', milestone.milestone_name)
        
        # Handle date conversion
        due_date_str = data.get('due_date')
        if due_date_str:
            try:
                milestone.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid date format'})
        
        # Handle amount conversion
        amount_str = data.get('amount')
        if amount_str:
            try:
                milestone.amount = float(amount_str)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Invalid amount format'})
        
        milestone.payment_reference = data.get('payment_reference', milestone.payment_reference)
        
        # Save the milestone (this will also update the status if overdue)
        milestone.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
def add_milestone(request, contract_id):
    """Add new payment milestone/invoice via AJAX"""
    from datetime import datetime
    
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    try:
        # Parse dates from strings
        invoice_date_str = data.get('invoice_date')
        due_date_str = data.get('due_date')
        
        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else None
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        
        # Parse amount
        amount = float(data.get('amount')) if data.get('amount') else 0
        
        milestone = PaymentMilestone.objects.create(
            contract=contract,
            milestone_name=data.get('milestone_name'),
            invoice_date=invoice_date,
            due_date=due_date,
            amount=amount,
            status='pending'
        )
        
        return JsonResponse({'success': True, 'id': milestone.id})
        
    except (ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'error': f'Invalid data: {str(e)}'}, status=400)


def accounting(request):
    """Accounting page with reconciliation table."""
    # Get all contracts with milestones
    milestones = PaymentMilestone.objects.select_related('contract').all()
    
    context = {
        'milestones': milestones
    }
    return render(request, 'core/accounting.html', context)


@require_http_methods(["POST"])
def save_qbo_data(request):
    """Save QBO data for payment milestones."""
    if request.method == 'POST':
        data = json.loads(request.body)
        for update in data['updates']:
            milestone = PaymentMilestone.objects.get(id=update['id'])
            setattr(milestone, update['field'], update['value'])
            milestone.save()
        return JsonResponse({'status': 'success'})


@require_http_methods(["POST"])
def update_client_name(request, contract_id):
    """Update client name for a contract."""
    contract = get_object_or_404(Contract, id=contract_id)
    data = json.loads(request.body)
    
    contract.client_name = data.get('value', '')
    contract.save()
    
    return JsonResponse({'success': True})


def hubspot_sync(request):
    """HubSpot Sync page view"""
    
    # Handle file upload
    if request.method == 'POST' and request.FILES.get('hubspot_file'):
        file = request.FILES['hubspot_file']
        
        # Import the HubSpotImporter
        from core.services.hubspot_importer import HubSpotImporter
        
        importer = HubSpotImporter()
        result = importer.import_file(file, request.user)
        
        if result['success']:
            messages.success(request, f"Successfully imported {result['count']} deals")
        else:
            messages.error(request, f"Import failed: {result.get('error', 'Unknown error')}")
            
        # Redirect to same page to show results
        return redirect('core:hubspot_sync')
    
    # Get deals and contracts
    deals = HubSpotDeal.objects.all().prefetch_related('matches__contract')
    contracts = Contract.objects.all().order_by('-upload_date')

    # Create lookup dictionary for matched contracts
    matched_contracts = {}
    for deal in deals:
        matched_match = next((match for match in deal.matches.all() if match.is_active), None)
        if matched_match:
            matched_contracts[deal.id] = matched_match.contract_id

    # Calculate stats
    letter_sent_count = deals.filter(stage='Engagement Letter Sent').count()
    closed_won_count = deals.filter(stage__icontains="Closed Won").count()
    unmatched_count = deals.exclude(matches__is_active=True).count()

    context = {
        'deals': deals,
        'contracts': contracts,
        'matched_contracts': matched_contracts,
        'letter_sent_count': letter_sent_count,
        'closed_won_count': closed_won_count,
        'unmatched_count': unmatched_count,
    }
    return render(request, 'core/hubspot_sync.html', context)


@require_POST
def match_hubspot_deal(request):
    """Create or update a HubSpotDealMatch record."""
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid JSON payload'},
            status=400,
        )

    deal_id = data.get('deal_id')
    contract_id = data.get('contract_id')

    if not deal_id:
        return JsonResponse(
            {
                'status': 'error',
                'message': 'deal_id is required',
            },
            status=400,
        )

    try:
        deal = HubSpotDeal.objects.get(pk=deal_id)
    except HubSpotDeal.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Deal not found'},
            status=404,
        )

    if contract_id == 'unmatch':
        active_matches = HubSpotDealMatch.objects.filter(deal=deal, is_active=True)
        had_active_match = active_matches.exists()
        if had_active_match:
            active_matches.update(is_active=False)

        return JsonResponse(
            {
                'status': 'success',
                'action': 'unmatched',
                'had_active_match': had_active_match,
            }
        )

    if not contract_id:
        return JsonResponse(
            {
                'status': 'error',
                'message': 'contract_id is required',
            },
            status=400,
        )

    try:
        contract = Contract.objects.get(pk=contract_id)
    except Contract.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Contract not found'},
            status=404,
        )

    had_active_match = HubSpotDealMatch.objects.filter(deal=deal, is_active=True).exists()

    match, created = HubSpotDealMatch.objects.update_or_create(
        deal=deal,
        defaults={
            'contract': contract,
            'matched_by': request.user if request.user.is_authenticated else None,
            'is_active': True,
        },
    )

    return JsonResponse(
        {
            'status': 'success',
            'action': 'matched',
            'created': created,
            'match_id': match.id,
            'was_previously_matched': had_active_match,
        }
    )
