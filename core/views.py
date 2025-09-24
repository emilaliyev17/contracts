from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
import json
import logging
import os
import tempfile
from datetime import datetime, date, timedelta

from .models import Contract, PaymentMilestone, PaymentTerms, ContractClarification
from .services.contract_processor import ContractProcessor, ContractProcessingError
from .services.excel_exporter import ExcelExporter
from django.db import models

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


def contract_list(request):
    """List all contracts."""
    contracts = Contract.objects.all()
    context = {
        'contracts': contracts,
    }
    return render(request, 'core/contract_list.html', context)


def contract_detail(request, contract_id):
    """Detail view for a specific contract."""
    contract = get_object_or_404(Contract, id=contract_id)
    payment_milestones = contract.payment_milestones.all()
    
    context = {
        'contract': contract,
        'payment_milestones': payment_milestones,
        'payment_terms': getattr(contract, 'payment_terms', None),
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


def clarifications_list(request):
    """List all clarification questions (pending and ready to apply)."""
    # Get all clarifications with related contract info
    all_clarifications = ContractClarification.objects.select_related('contract').order_by('-created_at')
    
    # Separate into pending and answered groups
    contracts_with_pending = {}
    contracts_ready_to_apply = {}
    
    # Get all contracts with clarifications
    contracts_with_clarifs = set(all_clarifications.values_list('contract_id', flat=True))
    
    for contract_id in contracts_with_clarifs:
        contract_clarifs = all_clarifications.filter(contract_id=contract_id)
        contract = contract_clarifs.first().contract
        
        pending_clarifs = contract_clarifs.filter(answered=False)
        answered_clarifs = contract_clarifs.filter(answered=True)
        
        if pending_clarifs.exists():
            # Contract has pending clarifications
            contracts_with_pending[contract_id] = {
                'contract': contract,
                'clarifications': list(pending_clarifs),
                'answered_count': answered_clarifs.count(),
                'total_count': contract_clarifs.count()
            }
        elif answered_clarifs.exists() and contract.status == 'needs_clarification':
            # All clarifications answered but not yet applied
            contracts_ready_to_apply[contract_id] = {
                'contract': contract,
                'clarifications': list(answered_clarifs),
                'can_apply': True
            }
    
    context = {
        'contracts_with_pending': contracts_with_pending.values(),
        'contracts_ready_to_apply': contracts_ready_to_apply.values(),
        'total_pending': ContractClarification.objects.filter(answered=False).count(),
        'total_ready': len(contracts_ready_to_apply)
    }
    
    return render(request, 'core/clarifications.html', context)


@require_http_methods(["POST"])
def answer_clarification(request, clarification_id):
    """Save user's answer to a clarification question."""
    try:
        clarification = get_object_or_404(ContractClarification, id=clarification_id)
        
        # Get the answer from POST data
        answer = request.POST.get('answer', '').strip()
        
        if not answer:
            messages.error(request, 'Please provide an answer before submitting.')
            return redirect('core:clarifications')
        
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
    
    return redirect('core:clarifications')


@require_http_methods(["POST"])
def apply_contract_clarifications(request, contract_id):
    """Manually apply all answered clarifications to a contract."""
    try:
        contract = get_object_or_404(Contract, id=contract_id)
        
        # Check if all clarifications are answered
        unanswered = contract.clarifications.filter(answered=False).count()
        
        if unanswered > 0:
            messages.warning(
                request,
                f'Cannot apply clarifications. {unanswered} question(s) still need answers.'
            )
            return redirect('core:clarifications')
        
        # Apply clarifications
        updates_made = contract.apply_clarifications()
        
        # Update status if needed
        if contract.status == 'needs_clarification':
            contract.status = 'completed'
            contract.save()
        
        if updates_made:
            updates_summary = ', '.join(updates_made[:5])  # Show first 5 updates
            if len(updates_made) > 5:
                updates_summary += f' and {len(updates_made) - 5} more'
            
            messages.success(
                request,
                f'✅ Successfully applied clarifications to "{contract.contract_name}": {updates_summary}'
            )
        else:
            messages.info(
                request,
                f'No updates needed for contract "{contract.contract_name}".'
            )
        
        logger.info(f"Manually applied clarifications for contract {contract_id}")
        
    except Exception as e:
        logger.error(f"Error applying clarifications for contract {contract_id}: {str(e)}")
        messages.error(request, f'Failed to apply clarifications: {str(e)}')
    
    return redirect('core:clarifications')