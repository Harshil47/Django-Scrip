from django.urls import path
from .views import  purchase_view
from . import views

urlpatterns = [
    path('purchase/', purchase_view, name='purchase-page'),  # Handles GET request for rendering the form
    path('purchase-entry/', purchase_view, name='purchase_entry'),
    path('purchase-entry/<int:purchase_id>/', purchase_view, name='purchase_entry_with_id'),  # With ID
    path('current-stock/', views.current_stock_view, name='current_stock'),
    path('script-info/<str:script_name>/', views.script_info_view, name='script_info'),
    path('main-feature-statement/', views.main_feature_statement, name='main_feature_statement'),
    path('get-brokers/', views.get_brokers, name='get-brokers'),
    path('user-pl/', views.user_pl_view, name='user_pl_view'),
    path('purchase-history/', views.purchase_history, name='purchase_history'),
    path('purchase-history/delete/<int:purchase_id>/', views.delete_purchase, name='delete_purchase'),
    path('sales-history/', views.sales_history, name='sales_history'),
    path('sales/delete/<int:sale_id>/', views.delete_sale, name='delete_sale'),
    path('mehul/', views.mehul_statement, name='mehul_statement'),
    path('print-statement/', views.print_statement, name='print_statement'),
    path('split/', views.split_view, name='split_view'),
    path('split/<str:script>/', views.split_view, name='split_view'),
    path('split/submit/<str:script>', views.stock_split_view, name='split_submit'),
    path('bonus/', views.bonus_view, name='bonus_view'),
    path('bonus/<str:script>/', views.bonus_view, name='bonus_view'),
    path('bonus/submit/<str:script>', views.bonus_submit, name='bonus_submit'),
    path('add-primary-market-prices/', views.add_primary_market_prices, name='add-primary-market-prices'),
    path('purchase-summary/', views.purchase_summary, name='purchase_summary'),
    path('loan', views.loan_list, name='loan_list'),
    path('new_loan/', views.new_loan, name='new_loan'),
    path('new_payment/<int:loan_id>/', views.new_payment, name='new_payment'),
    path('principal_payment/new/<int:loan_id>/', views.new_principal_payment, name='new_principal_payment'),
    path('client-analysis/', views.client_specific_analysis, name='client_specific_analysis'),
]
