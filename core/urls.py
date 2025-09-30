from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('forecast/', views.forecast_view, name='forecast'),
    path('forecast/export/', views.export_forecast, name='export_forecast'),
    path('api/metrics/', views.contract_metrics, name='contract_metrics'),
    path('contracts/', views.contract_list, name='contract_list'),
    path('contracts/<int:contract_id>/', views.contract_detail, name='contract_detail'),
    path('contracts/<int:contract_id>/update-po/', views.update_po_info, name='update_po_info'),
    path('contracts/<int:contract_id>/update-type/', views.update_contract_type, name='update_contract_type'),
    path('contracts/<int:contract_id>/update-status/', views.update_contract_status, name='update_contract_status'),
    path('contracts/<int:contract_id>/update-dates/', views.update_contract_dates, name='update_contract_dates'),
    path('contracts/<int:contract_id>/update-milestone/', views.update_milestone, name='update_milestone'),
    path('contracts/<int:contract_id>/add-milestone/', views.add_milestone, name='add_milestone'),
    path('contract/<int:contract_id>/delete/', views.delete_contract, name='delete_contract'),
    path('upload/', views.upload_contract, name='upload_contract'),
    path('upload/status/<int:contract_id>/', views.upload_status, name='upload_status'),
    path('test-results/', views.test_results, name='test_results'),
    path('export-excel/', views.export_excel, name='export_excel'),
    path('check-contracts/', views.check_contracts, name='check_contracts'),
    path('clarifications/<int:clarification_id>/answer/', views.answer_clarification, name='answer_clarification'),
    path('contracts/<int:contract_id>/apply-clarifications/', views.apply_contract_clarifications, name='apply_contract_clarifications'),
    path('accounting/', views.accounting, name='accounting'),
    path('save-qbo-data/', views.save_qbo_data, name='save_qbo_data'),
    path('contracts/<int:contract_id>/update-client/', views.update_client_name, name='update_client_name'),
    path('hubspot-sync/', views.hubspot_sync, name='hubspot_sync'),
    path('match-hubspot-deal/', views.match_hubspot_deal, name='match_hubspot_deal'),
]
