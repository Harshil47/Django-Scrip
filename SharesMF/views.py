from django.shortcuts import render , redirect , get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from .models import Purchase, UserTable , Balance , Sale , TaxRate , Exemption, Broker , StockPrice , StockSplit , Adjustment , Bonus , PrimaryMarketPrice, ScriptINE, Client, Loan, Payment, PrincipalPayment
from .forms import StockSplitForm , BonusForm , PrimaryMarketPriceForm, LoanForm, PaymentForm, PrincipalPaymentForm
import json , requests
from django.db.models import Sum , Q  , F, ExpressionWrapper, DecimalField, Value, Case, When , FloatField , Count, Max, Subquery, OuterRef, Value , Window
from django.contrib import messages
from datetime import datetime , timedelta 
from decimal import Decimal
from django.contrib import messages 
from django.db import transaction, models
import traceback
from collections import defaultdict
from django.utils.timezone import now
from django.db.models.functions import ExtractYear
from datetime import date
from django.db.models.functions import Coalesce , TruncMonth
#import matplotlib.pyplot as plt
import io
import base64


def purchase_view(request, purchase_id=None):
    users = UserTable.objects.all()
    data_entry_users = UserTable.objects.filter(data_entry=True)
    brokers = Broker.objects.all()
    if purchase_id:
        # Fetch the purchase record to duplicate
        purchase = get_object_or_404(Purchase, pk=purchase_id)
        initial_data = {
            'purchase_date': purchase.purchase_date,
            'script': purchase.script,
            'type': purchase.type,
            'user_name': purchase.user.name,
            'qty': purchase.qty,
            'purchase_rate': purchase.purchase_rate,
            'broker': purchase.broker.name if purchase.broker else '',
            'mode': purchase.mode,
            'mehul': purchase.mehul,
            'entry': purchase.entry,
            'referenced_by': purchase.referenced_by,
        }
    else:
        initial_data = {}
    
    if request.method == 'POST':
        try:
            # Extract data from POST request
            purchase_date = request.POST['purchase_date']
            script = request.POST['script']
            purchase_type = request.POST['type']
            user_name = request.POST['user_name']
            qty = int(request.POST['qty'])
            purchase_rate = float(request.POST['purchase_rate'])
            broker_name = request.POST['broker']
            mode = request.POST['mode']
            mehul = request.POST['mehul'] == 'true'  # Convert string to boolean
            entry = request.POST['entry']
            referenced_by = request.POST['referenced_by']

            # Retrieve related objects
            user = UserTable.objects.get(name=user_name)
            broker = Broker.objects.get(name=broker_name) if broker_name else None

            # Create the purchase entry
            Purchase.objects.create(
                purchase_date=purchase_date,
                script=script,
                type=purchase_type,
                user=user,
                qty=qty,
                purchase_rate=purchase_rate,
                broker=broker,
                mode=mode,
                mehul=mehul,
                entry=entry,
                referenced_by=referenced_by
                
            )
            
            return render(request, 'purchase.html', {'success_message': 'Purchase added successfully!'})
        except UserTable.DoesNotExist:
            return render(request, 'purchase.html', {'error_message': 'User not found.'})
        except Broker.DoesNotExist:
            return render(request, 'purchase.html', {'error_message': 'Broker not found.'})
        except Exception as e:
            return render(request, 'purchase.html', {'error_message': str(e)})
    # Fetch data for dropdowns
    
    
    return render(request, 'purchase.html', {
        'initial_data': initial_data,
        'users': users,
        'data_entry_users': data_entry_users,
        'brokers': brokers
    })


def current_stock_view(request):
    
    # Get users for the user filter
    users = UserTable.objects.all()

    # Get selected user from the GET request (if provided)
    user_filter = request.GET.get('user', None)
    family_filter = request.GET.get('family', None)
    # Get the 'mehul' filter value from the GET request (default to 'False' or 'No')
    mehul_filter = request.GET.get('mehul', 'off') == 'on'
    purchase_mode_filter = request.GET.get('purchase_mode', None)
    
    # Aggregate balance records by script
    balance_records = Balance.objects.values('script').annotate(
        total_qty=Sum('qty'),
        total_amount=Sum('amount'),
        entry_count=Count('id')
    )
    if user_filter:
        balance_records = balance_records.filter(user__name=user_filter)
        
    # Filter by Family
    if family_filter:
        balance_records = balance_records.filter(user__family=family_filter)
        
    # Filter by 'mehul' if the 'mehul' filter is 'on'
    if mehul_filter:
        balance_records = balance_records.filter(purchase_id__mehul=True)  # Access 'mehul' in Purchase
        
    if purchase_mode_filter:
        balance_records = balance_records.filter(purchase_id__mode=purchase_mode_filter)
        
    # Calculate the total holding amount
    total_holding_amount = balance_records.aggregate(total=Sum('total_amount'))['total'] or 0
    

 
    # Logic to delete balance entries where qty == 0
    try:
        deleted_count, _ = Balance.objects.filter(qty=0).delete()
        if deleted_count > 0:
            print(f"DEBUG: Deleted {deleted_count} balance entries with qty=0.")
    except Exception as e:
        print(f"ERROR: Unable to delete balance entries - {e}")

    # Pass the aggregated data to the template
    context = {
        'balance_records': balance_records,
        'users': users,
        'user_filter': user_filter, 
        'family_filter': family_filter, 
        'mehul_filter': mehul_filter, 
        'purchase_mode_filter': purchase_mode_filter,
        'total_holding_amount': total_holding_amount,
    }
    return render(request, 'current_stock.html', context)

def script_info_view(request, script_name):
    # Get all unique users for the dropdown
    users = UserTable.objects.all()

    # Get the selected user from the request (if any)
    selected_user = request.GET.get('user', None)

    # Fetch balance records for the given script and optionally filter by user
    balance_records = Balance.objects.filter(script=script_name)
    if selected_user:
        balance_records = balance_records.filter(user__name=selected_user)

    # Calculate total stock quantity
    total_qty = sum(record.qty for record in balance_records)

    if request.method == "POST":
        sell_qty = request.POST.get('sell_qty')
        try:
            sell_quantity = int(sell_qty)  # Convert to an integer
        except (TypeError, ValueError):  # Handle cases where the input is invalid
            sell_quantity = 0
        sale_rate = request.POST.get('sale_rate')
        try:
            sale_rate = float(sale_rate)  # Convert to a float
        except (TypeError, ValueError):
            sale_rate = None
            
        # Get the sale date from the form
        sale_date = request.POST.get('sale_date')
        try:
            sale_date = datetime.strptime(sale_date, '%Y-%m-%d').date()  # Convert to date object
        except (TypeError, ValueError):
            sale_date = None  # Invalid date input, handle this case later
        gf_rate = request.POST.get('gf_rate')

            
        if sell_quantity > total_qty:
            messages.error(request, "Insufficient stock to sell. Please check your available quantity.")
        else:
            # Process sale using FIFO
            remaining_qty = sell_quantity
            for record in balance_records.order_by('purchase_id__purchase_date'):
                if remaining_qty <= 0:
                    break
                qty_to_sell = min(record.qty, remaining_qty)
                
                # Create a sale entry
                gf_rate = Decimal(gf_rate) if gf_rate else None
                
                Sale.objects.create(
                    sale_date= sale_date,
                    purchase_id=record.purchase_id,
                    script=script_name,
                    user=record.user,
                    qty=qty_to_sell,
                    sale_rate=sale_rate,
                    gf_rate=gf_rate,
                )
                
                # Update balance record
                record.qty -= qty_to_sell
                print(record.qty)
                record.save()

                remaining_qty -= qty_to_sell

            messages.success(request, f"Successfully sold {sell_qty} stocks.")
        return redirect('script_info', script_name=script_name)
    
    # Fetch last 5 sales for the given script
    past_sales = Sale.objects.filter(script=script_name).order_by('-sale_date')[:5]

    context = {
        'script_name': script_name,
        'balance_records': balance_records,
        'users': users,
        'selected_user': selected_user,
        'total_qty': total_qty,
        'past_sales': past_sales, 
    }
    return render(request, 'script_info.html', context)

def main_feature_statement(request):
    # Getting the current date for date range filters (can be adjusted for custom range)
    today = datetime.today()

    # Get users for the user filter
    users = UserTable.objects.all()
    brokers = Broker.objects.all()

    # Default date range is the last 30 days
    start_date = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    # Get selected user
    user_filter = request.GET.get('user', None)
    broker_filter = request.GET.get('broker', None)
    type_filter = request.GET.get('type', None) 
    mode_filter = request.GET.get('mode', None) 

    # Filter Sale objects based on selected user and date range
    sales_query = Sale.objects.filter(sale_date__range=[start_date, end_date])

    if user_filter:
        sales_query = sales_query.filter(user__name=user_filter)
        
    if broker_filter:
        sales_query = sales_query.filter(purchase_id__broker__name=broker_filter)
        
    if type_filter:  # Apply the new filter for type
        sales_query = sales_query.filter(purchase_id__type=type_filter)
        
    if mode_filter:  # Apply mode filter
        sales_query = sales_query.filter(purchase_id__mode=mode_filter)

        
    # Annotate with derived values
    sales_query = sales_query.annotate(
        purchase_rate=F('purchase_id__purchase_rate'),
        broker=F('purchase_id__broker'),
        gf_amount=ExpressionWrapper(
            F('gf_rate') * F('qty'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    )
        
    # Tax rates for Speculation, Long, and Short
    tax_rates = {tax_rate.profit: tax_rate.percent for tax_rate in TaxRate.objects.all()}
    # Short Term Profit/Loss
    #short_term_sales = sales_query.filter(sale_date__lt=F('purchase_id__purchase_date') + timedelta(days=365))
    short_term_sales = sales_query.filter(
    sale_date__gte=F('purchase_id__purchase_date') + timedelta(days=1),
    sale_date__lt=F('purchase_id__purchase_date') + timedelta(days=365)
)

    # Calculate totals using the calculate_purchase_total method
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in short_term_sales)

    
    short_term_summary = short_term_sales.aggregate(
        total_sale_amount=Sum('sale_amount'),
        total_short_profit=Sum('short_profit'),
        total_short_loss=Sum('short_loss'),
        total_short_net=Sum(F('short_profit') - F('short_loss')- F('tax')),
    )
    # Include the manually calculated purchase total
    short_term_summary['total_purchase_amount'] = total_purchase_amount
    short_term_profit = short_term_summary['total_short_profit'] or 0
    short_term_loss = short_term_summary['total_short_loss'] or 0
    short_term_tax = max(0,(short_term_profit - short_term_loss) * (Decimal(tax_rates.get('Short', 0)) / Decimal(100)))
    # Calculate total short-term net profit
    total_short_net = short_term_profit - short_term_loss - short_term_tax

    # Update the short-term summary
    short_term_summary['total_short_net'] = total_short_net

    # Long Term Profit/Loss
    long_term_sales = sales_query.filter(sale_date__gte=F('purchase_id__purchase_date') + timedelta(days=365))
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in long_term_sales)
    long_term_summary = long_term_sales.aggregate(
        
        total_sale_amount=Sum('sale_amount'),
        total_long_profit=Sum('long_profit'),
        total_long_loss=Sum('long_loss'),
    )
    long_term_summary['total_purchase_amount'] = total_purchase_amount
    long_term_profit = long_term_summary['total_long_profit'] or 0
    long_term_loss = long_term_summary['total_long_loss'] or 0
    # Fetch the exemption amount from the Exemption table
    try:
        exemption = Exemption.objects.get(long='longTerm') 
        exemption_amount = Decimal(exemption.deduct)
    except Exemption.DoesNotExist:
        exemption_amount = Decimal(0)  # Default to 0 if no exemption record is found

    # Update the long-term tax calculation logic
    taxable_long_term_profit = max(Decimal(0), long_term_profit - long_term_loss - exemption_amount)
    long_term_tax = max(0,taxable_long_term_profit * (Decimal(tax_rates.get('Long', 0)) / Decimal(100)))
    # Calculate total long-term net profit
    total_long_net = long_term_profit - long_term_loss - long_term_tax

# Update long-term summary
    long_term_summary['total_long_net'] = total_long_net
    #long_term_tax = (long_term_profit - long_term_loss) * (Decimal(tax_rates.get('Long', 0)) / Decimal(100))
    

   # Speculation Profit/Loss (non-null and greater than 0 in spec_profit or spec_loss)
    speculation_sales = sales_query.filter(
        Q(spec_profit__gt=0) | Q(spec_loss__gt=0)  # Either spec_profit or spec_loss greater than 0
    )
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in speculation_sales)
    speculation_summary = speculation_sales.aggregate(
        
        total_sale_amount=Sum('sale_amount'),
        total_spec_profit=Sum('spec_profit'),
        total_spec_loss=Sum('spec_loss'),
    )
    speculation_summary['total_purchase_amount'] = total_purchase_amount
    speculation_profit = speculation_summary['total_spec_profit'] or 0
    speculation_loss = speculation_summary['total_spec_loss'] or 0
    speculation_tax = max(0,(speculation_profit - speculation_loss) * (Decimal(tax_rates.get('Speculation', 0)) / Decimal(100)))
    # Calculate total speculation net profit
    total_spec_net = speculation_profit - speculation_loss - speculation_tax
    speculation_summary['total_spec_net'] = total_spec_net

    context = {
        'users': users,
        'start_date': start_date,
        'end_date': end_date,
        'brokers': brokers,
        'short_term_sales': short_term_sales,
        'long_term_sales': long_term_sales,
        'speculation_sales': speculation_sales,
        'short_term_summary': short_term_summary,
        'long_term_summary': long_term_summary,
        'speculation_summary': speculation_summary,
        'short_term_tax': short_term_tax,
        'long_term_tax': long_term_tax,
        'speculation_tax': speculation_tax,
        'type_filter': type_filter,
        'mode_filter': mode_filter,
    }

    return render(request, 'main_feature_statement.html', context)

def get_brokers(request):
    if request.method == 'GET':
        brokers = Broker.objects.all()
        #brokers_data = [{"id": broker.id, "name": broker.name} for broker in brokers]
        brokers_data = [{"name": broker.name} for broker in brokers]
        return JsonResponse(brokers_data, safe=False)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

def user_pl_view(request):
    # Get today's date
    today = datetime.today()

    # Default date range is the last 30 days
    start_date = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    print(f"Start date: {start_date}, End date: {end_date}")  # Debugging start and end dates
     # Retrieve tax rates from the TaxRate table
    try:
        short_tax_rate = TaxRate.objects.get(profit="Short").percent
        long_tax_rate = TaxRate.objects.get(profit="Long").percent
        spec_tax_rate = TaxRate.objects.get(profit="Speculation").percent
    except TaxRate.DoesNotExist:
        return render(request, 'user_pl.html', {'error': 'Tax rates not defined.'})
    print(f"Short tax rate: {short_tax_rate}, Long tax rate: {long_tax_rate}, Spec tax rate: {spec_tax_rate}")  # Debugging tax rates

    # Filter sales within the date range
    sales = Sale.objects.filter(sale_date__range=[start_date, end_date])
    
     # Fetch the total exemption deduction
    exemption_deduction = Decimal(
        Exemption.objects.aggregate(total_deduct=Sum('deduct'))['total_deduct'] or 0
    )
    print(f"Exemption deduction: {exemption_deduction}")


    # Aggregate records by user
    aggregated_sales = sales.values('user').annotate(
        total_short_profit=Sum('short_profit'),
        total_short_loss=Sum('short_loss'),
        total_long_profit=Sum('long_profit'),
        total_long_loss=Sum('long_loss'),
        total_spec_profit=Sum('spec_profit'),
        total_spec_loss=Sum('spec_loss'),
        spec_net=F('total_spec_profit') - F('total_spec_loss'),
        short_net=F('total_short_profit') - F('total_short_loss')
   ).annotate(
    # Intermediate calculation for Part 1 Tax (without using Sum directly)
    part_1_tax_raw=(
        (F('total_short_profit') - F('total_short_loss')) * Value(short_tax_rate / 100, output_field=DecimalField()) +
        (F('total_spec_profit') - F('total_spec_loss')) * Value(spec_tax_rate / 100, output_field=DecimalField())
    ),
    # Intermediate calculation for Part 2 Tax with Exemption Deduction
    part_2_raw_tax=(
        (F('total_long_profit') - F('total_long_loss') - Value(exemption_deduction, output_field=DecimalField())) *
        Value(long_tax_rate / 100, output_field=DecimalField())
    ),
).annotate(
    # Ensure part_1_tax is non-negative
    part_1_tax=Case(
        When(part_1_tax_raw__gte=0, then=F('part_1_tax_raw')),
        default=Value(0, output_field=DecimalField())
    ),
    # Ensure part_2_raw_tax is non-negative
    part_2_tax_adjusted=Case(
        When(part_2_raw_tax__gt=0, then=F('part_2_raw_tax')),
        default=Value(0, output_field=DecimalField())
    ),
    # Final total tax aggregation
    total_tax=F('part_1_tax') + F('part_2_tax_adjusted'),
    # Calculate 'Net'
    net=(
            (F('total_short_profit') + F('total_long_profit') + F('total_spec_profit')) -
            (F('total_short_loss') + F('total_long_loss') + F('total_spec_loss')+F('total_tax'))
        ),
        # Define the deduction_left calculation with conditional logic
deduction_left=(
            Value(exemption_deduction, output_field=DecimalField()) + F('total_long_loss') - F('total_long_profit')
        )
)

    
    # Calculate totals for the new fields
    total_net = aggregated_sales.aggregate(Sum('net'))['net__sum'] or 0
    total_deduction_left = aggregated_sales.aggregate(Sum('deduction_left'))['deduction_left__sum'] or 0
    # Calculate totals
    total_short_profit = aggregated_sales.aggregate(Sum('total_short_profit'))['total_short_profit__sum'] or 0
    total_short_loss = aggregated_sales.aggregate(Sum('total_short_loss'))['total_short_loss__sum'] or 0
    total_long_profit = aggregated_sales.aggregate(Sum('total_long_profit'))['total_long_profit__sum'] or 0
    total_long_loss = aggregated_sales.aggregate(Sum('total_long_loss'))['total_long_loss__sum'] or 0
    total_spec_profit = aggregated_sales.aggregate(Sum('total_spec_profit'))['total_spec_profit__sum'] or 0
    total_spec_loss = aggregated_sales.aggregate(Sum('total_spec_loss'))['total_spec_loss__sum'] or 0
    #total_tax = aggregated_sales.aggregate(Sum('total_tax'))['total_tax__sum'] or 0
    total_spec_net = aggregated_sales.aggregate(Sum('spec_net'))['spec_net__sum'] or 0
    total_short_net = aggregated_sales.aggregate(Sum('short_net'))['short_net__sum'] or 0
    
    total_tax = aggregated_sales.aggregate(Sum('total_tax'))['total_tax__sum'] or Decimal(0)
    


    context = {
        'aggregated_sales': aggregated_sales,
        'start_date': start_date,
        'end_date': end_date,
        'total_short_profit': total_short_profit,
        'total_short_loss': total_short_loss,
        'total_long_profit': total_long_profit,
        'total_long_loss': total_long_loss,
        'total_spec_profit': total_spec_profit,
        'total_spec_loss': total_spec_loss,
        'total_tax': total_tax,
        'total_net': total_net,
        'total_deduction_left': total_deduction_left,
        'total_spec_net': total_spec_net,
        'total_short_net': total_short_net
    }

    return render(request, 'user_pl.html', context)

def purchase_history(request):
    purchases = Purchase.objects.all()
    return render(request, 'purchase_history.html', {'purchases': purchases})

def delete_purchase(request, purchase_id):
    purchase = get_object_or_404(Purchase, purchase_id=purchase_id)
    if request.method == "POST":
        purchase.delete()
        messages.success(request, f"Purchase {purchase_id} has been deleted successfully.")
        return redirect('purchase_history')
    return redirect('purchase_history')

def sales_history(request):
    sales = Sale.objects.all()
    context = {
        'sales': sales,
    }
    return render(request, 'sales_history.html', context)

def delete_sale(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    sale.delete()
    return redirect('sales_history')

def mehul_statement(request):
    # Getting the current date for date range filters (can be adjusted for custom range)
    today = datetime.today()

    # Get users for the user filter
    users = UserTable.objects.all()
    brokers = Broker.objects.all()

    # Default date range is the last 30 days
    start_date = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    # Get selected user
    user_filter = request.GET.get('user', None)
    broker_filter = request.GET.get('broker', None)
    type_filter = request.GET.get('type', None) 

    # Filter Sale objects based on selected user and date range
    sales_query = Sale.objects.filter(sale_date__range=[start_date, end_date])
    
    # Filter Purchase objects where 'mehul' is True
    sales_query = sales_query.filter(purchase_id__mehul=True)

    if user_filter:
        sales_query = sales_query.filter(user__name=user_filter)
        
    if broker_filter:
        sales_query = sales_query.filter(purchase_id__broker__name=broker_filter)
        
    if type_filter:  # Apply the new filter for type
        sales_query = sales_query.filter(purchase_id__type=type_filter)

        
    # Annotate with derived values
    sales_query = sales_query.annotate(
        purchase_rate=F('purchase_id__purchase_rate'),
        broker=F('purchase_id__broker'),
        gf_amount=ExpressionWrapper(
            F('gf_rate') * F('qty'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    )
        
    # Tax rates for Speculation, Long, and Short
    tax_rates = {tax_rate.profit: tax_rate.percent for tax_rate in TaxRate.objects.all()}
    # Short Term Profit/Loss
    #short_term_sales = sales_query.filter(sale_date__lt=F('purchase_id__purchase_date') + timedelta(days=365))
    short_term_sales = sales_query.filter(
    sale_date__gte=F('purchase_id__purchase_date') + timedelta(days=1),
    sale_date__lt=F('purchase_id__purchase_date') + timedelta(days=365)
)

    # Calculate totals using the calculate_purchase_total method
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in short_term_sales)

    
    short_term_summary = short_term_sales.aggregate(
        total_sale_amount=Sum('sale_amount'),
        total_short_profit=Sum('short_profit'),
        total_short_loss=Sum('short_loss'),
        total_short_net=Sum(F('short_profit') - F('short_loss')- F('tax')),
    )
    # Include the manually calculated purchase total
    short_term_summary['total_purchase_amount'] = total_purchase_amount
    short_term_profit = short_term_summary['total_short_profit'] or 0
    short_term_loss = short_term_summary['total_short_loss'] or 0
    short_term_tax = max(0,(short_term_profit - short_term_loss) * (Decimal(tax_rates.get('Short', 0)) / Decimal(100)))

    # Long Term Profit/Loss
    long_term_sales = sales_query.filter(sale_date__gte=F('purchase_id__purchase_date') + timedelta(days=365))
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in long_term_sales)
    long_term_summary = long_term_sales.aggregate(
        
        total_sale_amount=Sum('sale_amount'),
        total_long_profit=Sum('long_profit'),
        total_long_loss=Sum('long_loss'),
        total_long_net=Sum(F('long_profit') - F('long_loss') - F('tax')),
    )
    long_term_summary['total_purchase_amount'] = total_purchase_amount
    long_term_profit = long_term_summary['total_long_profit'] or 0
    long_term_loss = long_term_summary['total_long_loss'] or 0
    

    # Update the long-term tax calculation logic
    taxable_long_term_profit = max(Decimal(0), long_term_profit - long_term_loss )
    long_term_tax = max(0,taxable_long_term_profit * (Decimal(tax_rates.get('Long', 0)) / Decimal(100)))
    #long_term_tax = (long_term_profit - long_term_loss) * (Decimal(tax_rates.get('Long', 0)) / Decimal(100))
    

   # Speculation Profit/Loss (non-null and greater than 0 in spec_profit or spec_loss)
    speculation_sales = sales_query.filter(
        Q(spec_profit__gt=0) | Q(spec_loss__gt=0)  # Either spec_profit or spec_loss greater than 0
    )
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in speculation_sales)
    speculation_summary = speculation_sales.aggregate(
        
        total_sale_amount=Sum('sale_amount'),
        total_spec_profit=Sum('spec_profit'),
        total_spec_loss=Sum('spec_loss'),
        total_spec_net=Sum(F('spec_profit') - F('spec_loss') - F('tax')),
    )
    speculation_summary['total_purchase_amount'] = total_purchase_amount
    speculation_profit = speculation_summary['total_spec_profit'] or 0
    speculation_loss = speculation_summary['total_spec_loss'] or 0
    speculation_tax = max(0,(speculation_profit - speculation_loss) * (Decimal(tax_rates.get('Speculation', 0)) / Decimal(100)))

    context = {
        'users': users,
        'start_date': start_date,
        'end_date': end_date,
        'brokers': brokers,
        'short_term_sales': short_term_sales,
        'long_term_sales': long_term_sales,
        'speculation_sales': speculation_sales,
        'short_term_summary': short_term_summary,
        'long_term_summary': long_term_summary,
        'speculation_summary': speculation_summary,
        'short_term_tax': short_term_tax,
        'long_term_tax': long_term_tax,
        'speculation_tax': speculation_tax,
        'type_filter': type_filter,
    }

    return render(request, 'mehul_statement.html', context)

def print_statement(request):
    # Getting the current date for date range filters (can be adjusted for custom range)
    today = datetime.today()

    # Get users for the user filter
    users = UserTable.objects.all()
    brokers = Broker.objects.all()

    # Default date range is the last 30 days
    start_date = request.GET.get('start_date', (today - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    # Get selected user
    user_filter = request.GET.get('user', None)
    broker_filter = request.GET.get('broker', None)
    type_filter = request.GET.get('type', None) 

    # Filter Sale objects based on selected user and date range
    sales_query = Sale.objects.filter(sale_date__range=[start_date, end_date])

    if user_filter:
        sales_query = sales_query.filter(user__name=user_filter)
        
    if broker_filter:
        sales_query = sales_query.filter(purchase_id__broker__name=broker_filter)
        
    if type_filter:  # Apply the new filter for type
        sales_query = sales_query.filter(purchase_id__type=type_filter)

        
    # Annotate with derived values
    sales_query = sales_query.annotate(
        purchase_rate=F('purchase_id__purchase_rate'),
        broker=F('purchase_id__broker'),
        ine=Subquery(
        ScriptINE.objects.filter(script=OuterRef('script')).values('ine')[:1]
    ),
        gf_amount=ExpressionWrapper(
            F('gf_rate') * F('qty'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    )
        
    # Tax rates for Speculation, Long, and Short
    tax_rates = {tax_rate.profit: tax_rate.percent for tax_rate in TaxRate.objects.all()}
    # Short Term Profit/Loss
    #short_term_sales = sales_query.filter(sale_date__lt=F('purchase_id__purchase_date') + timedelta(days=365))
    short_term_sales = sales_query.filter(
    sale_date__gte=F('purchase_id__purchase_date') + timedelta(days=1),
    sale_date__lt=F('purchase_id__purchase_date') + timedelta(days=365)
)

    # Calculate totals using the calculate_purchase_total method
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in short_term_sales)

    
    short_term_summary = short_term_sales.aggregate(
        total_sale_amount=Sum('sale_amount'),
        total_short_profit=Sum('short_profit'),
        total_short_loss=Sum('short_loss'),
        total_short_net=Sum(F('short_profit') - F('short_loss')- F('tax')),
    )
    # Include the manually calculated purchase total
    short_term_summary['total_purchase_amount'] = total_purchase_amount
    short_term_profit = short_term_summary['total_short_profit'] or 0
    short_term_loss = short_term_summary['total_short_loss'] or 0
    short_term_tax = max(0,(short_term_profit - short_term_loss) * (Decimal(tax_rates.get('Short', 0)) / Decimal(100)))
    # Calculate total short-term net profit
    total_short_net = short_term_profit - short_term_loss - short_term_tax

    # Update the short-term summary
    short_term_summary['total_short_net'] = total_short_net

    # Long Term Profit/Loss
    long_term_sales = sales_query.filter(sale_date__gte=F('purchase_id__purchase_date') + timedelta(days=365))
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in long_term_sales)
    long_term_summary = long_term_sales.aggregate(
        
        total_sale_amount=Sum('sale_amount'),
        total_long_profit=Sum('long_profit'),
        total_long_loss=Sum('long_loss'),
    )
    long_term_summary['total_purchase_amount'] = total_purchase_amount
    long_term_profit = long_term_summary['total_long_profit'] or 0
    long_term_loss = long_term_summary['total_long_loss'] or 0
    # Fetch the exemption amount from the Exemption table
    try:
        exemption = Exemption.objects.get(long='longTerm') 
        exemption_amount = Decimal(exemption.deduct)
    except Exemption.DoesNotExist:
        exemption_amount = Decimal(0)  # Default to 0 if no exemption record is found

    # Update the long-term tax calculation logic
    taxable_long_term_profit = max(Decimal(0), long_term_profit - long_term_loss - exemption_amount)
    long_term_tax = max(0,taxable_long_term_profit * (Decimal(tax_rates.get('Long', 0)) / Decimal(100)))
    # Calculate total long-term net profit
    total_long_net = long_term_profit - long_term_loss - long_term_tax

# Update long-term summary
    long_term_summary['total_long_net'] = total_long_net
    #long_term_tax = (long_term_profit - long_term_loss) * (Decimal(tax_rates.get('Long', 0)) / Decimal(100))
    

   # Speculation Profit/Loss (non-null and greater than 0 in spec_profit or spec_loss)
    speculation_sales = sales_query.filter(
        Q(spec_profit__gt=0) | Q(spec_loss__gt=0)  # Either spec_profit or spec_loss greater than 0
    )
    total_purchase_amount = sum(sale.calculate_purchase_total() or 0 for sale in speculation_sales)
    speculation_summary = speculation_sales.aggregate(
        
        total_sale_amount=Sum('sale_amount'),
        total_spec_profit=Sum('spec_profit'),
        total_spec_loss=Sum('spec_loss'),
    )
    speculation_summary['total_purchase_amount'] = total_purchase_amount
    speculation_profit = speculation_summary['total_spec_profit'] or 0
    speculation_loss = speculation_summary['total_spec_loss'] or 0
    speculation_tax = max(0,(speculation_profit - speculation_loss) * (Decimal(tax_rates.get('Speculation', 0)) / Decimal(100)))
    # Calculate total speculation net profit
    total_spec_net = speculation_profit - speculation_loss - speculation_tax
    speculation_summary['total_spec_net'] = total_spec_net

    context = {
        'users': users,
        'start_date': start_date,
        'end_date': end_date,
        'brokers': brokers,
        'short_term_sales': short_term_sales,
        'long_term_sales': long_term_sales,
        'speculation_sales': speculation_sales,
        'short_term_summary': short_term_summary,
        'long_term_summary': long_term_summary,
        'speculation_summary': speculation_summary,
        'short_term_tax': short_term_tax,
        'long_term_tax': long_term_tax,
        'speculation_tax': speculation_tax,
        'type_filter': type_filter,
    }

    return render(request, 'print_statement.html', context)

def split_view(request,script):
    context = {'script': script}
    return render(request, 'split_form.html', context)

@transaction.atomic
def stock_split_view(request,script):
    if request.method == 'POST':
        print("Form submission detected")  # Debugging
        print("POST data received:", request.POST)
        form = StockSplitForm(request.POST)
        if form.is_valid():
            print("Form is valid")
            script = form.cleaned_data['script']
            split_date = form.cleaned_data['split_date']
            ratio = form.cleaned_data['ratio']

            print(f"Script: {script}, Split Date: {split_date}, Ratio: {ratio}")
            # Create StockSplit entry
            split = StockSplit.objects.create(script=script, split_date=split_date, ratio=ratio)

            # Handle the Purchase Table Update
            try:
                with transaction.atomic():
                    purchases = Purchase.objects.filter(script=script)
                    for purchase in purchases:
                        # Calculate sold quantity
                        sold_qty = Sale.objects.filter(purchase_id=purchase).aggregate(
                            total_sold=models.Sum('qty')
                        )['total_sold'] or 0
                        print(f"Sold quantity for purchase {purchase.purchase_id}: {sold_qty}")  # Debugging

                        remaining_qty = purchase.qty - sold_qty
                        print(f"Remaining quantity: {remaining_qty}")  # Debugging
                        if remaining_qty > 0:
                            # Update current record for sold quantity
                            purchase.qty = sold_qty
                            purchase.save()

                            # Create a new record for split quantity
                            Purchase.objects.create(
                                purchase_date=purchase.purchase_date,
                                script=purchase.script,
                                type=purchase.type,
                                mode=purchase.mode,
                                user=purchase.user,
                                qty=int(remaining_qty * ratio),
                                
                                purchase_rate=purchase.purchase_rate / Decimal(ratio),
                                purchase_amount=Decimal(remaining_qty) * Decimal(ratio) * (purchase.purchase_rate / Decimal(ratio)),

                                broker=purchase.broker,
                                mehul=purchase.mehul,
                                entry=purchase.entry,
                                referenced_by=purchase.referenced_by,
                            )
                        else:
                            print(f"Deleting purchase entry {purchase.purchase_id} as quantity is 0")
                            purchase.delete()
                    balances = Balance.objects.filter(script=script)
                    for balance in balances:
                        purchase_id = balance.purchase_id_id
                        purchase_qty = Purchase.objects.get(purchase_id=purchase_id).qty
                        sold_qty = Sale.objects.filter(purchase_id=purchase_id).aggregate(
                            total_sold=models.Sum('qty')
                        )['total_sold'] or 0
                        updated_qty = purchase_qty - sold_qty
                        print(f"Updating balance for {balance.script}, Purchase ID {purchase_id}: Qty = {updated_qty}")
                        balance.qty = updated_qty
                        balance.save()
            except Exception as e:
                traceback.print_exc()
                # Add error handling, e.g., returning a message to the user
                return render(request, 'error_page.html', {'error': str(e)})
            return redirect('current_stock')  # Redirect to a success page
        else:
            print("Form is invalid:", form.errors)
    else:
        print("Rendering GET request for form")
        form = StockSplitForm()
    return render(request, 'split_form.html', {'form': form,'script': script})

def bonus_view(request, script):
    """Render the bonus form."""
    context = {'script': script}
    return render(request, 'bonus_form.html', context)

@transaction.atomic
def bonus_submit(request, script):
    """Handle bonus logic on form submission."""
    if request.method == 'POST':
        form = BonusForm(request.POST)
        if form.is_valid():
            script = form.cleaned_data['script']
            bonus_date = form.cleaned_data['bonus_date']
            ratio = form.cleaned_data['ratio']
            
            # Save the bonus information to the Bonus table
            Bonus.objects.create(script=script, bonus_date=bonus_date, ratio=ratio)

            # Fetch purchases for the given script
            purchases = Purchase.objects.filter(script=script).order_by('purchase_date')  # Ensure sorted by date

            for purchase in purchases:
                balance_qty = Balance.objects.filter(purchase_id=purchase).aggregate(
                    total_balance=models.Sum('qty')
                )['total_balance'] or 0

                if balance_qty > 0:
                    new_qty = balance_qty * ratio

                    # Handle adjustment for purchase amount
                    if purchase.purchase_amount > 1:
                        Adjustment.objects.create(purchase_id=purchase, adjustment_value=-1)
                        purchase.purchase_amount -= 1
                        purchase.save()
                        
                        # Update related balances
                        related_balances = Balance.objects.filter(purchase_id=purchase)
                        for balance in related_balances:
                            balance.save()
                    else:
                        # Find another record with a purchase_amount > 0
                        alternative_purchase = (
                            Purchase.objects.filter(
                                script=script,
                                user=purchase.user,
                                purchase_amount__gt=0
                            )
                            .exclude(purchase_id=purchase.purchase_id)  # Avoid the current purchase
                            .order_by('purchase_date')  # Prefer older records
                            .first()
                        )

                        if alternative_purchase:
                            Adjustment.objects.create(purchase_id=alternative_purchase, adjustment_value=-1)
                            alternative_purchase.purchase_amount -= 1
                            alternative_purchase.save()
                            
                            # Update related balances for the alternative purchase
                            alternative_balances = Balance.objects.filter(purchase_id=alternative_purchase)
                            for balance in alternative_balances:
                                balance.save()
                        else:
                            # Abort the operation if no suitable alternative is found
                            raise Exception(
                                f"No purchase with positive amount found for script '{script}' and user '{purchase.user}'. Bonus operation aborted."
                            )
                    purchase.save(update_fields=[])
                    
                    related_balances = Balance.objects.filter(purchase_id=purchase)
                    for balance in related_balances:
                        balance.save()

                    # Create a new bonus record in the Purchase table
                    bonus_purchase = Purchase.objects.create(
                        purchase_date=purchase.purchase_date,
                        script=script,
                        type=purchase.type,
                        mode=purchase.mode,
                        user=purchase.user,
                        qty=new_qty,
                        purchase_rate=0,
                        purchase_amount=0,  # Set amount to 0
                        broker=purchase.broker,
                        mehul=purchase.mehul,
                        entry="Bonus",
                        referenced_by="System",
                    )

                    # Record adjustment for the bonus entry
                    Adjustment.objects.create(purchase_id=bonus_purchase, adjustment_value=1)
                    
                    # Trigger `save` on related `Balance` instances for the bonus purchase
                    bonus_related_balances = Balance.objects.filter(purchase_id=bonus_purchase)
                    for balance in bonus_related_balances:
                        balance.save()

                   
        return redirect('current_stock')  # Redirect to a success page
    else:
        form = BonusForm()
    return render(request, 'bonus_form.html', {'form': form, 'script': script})

def add_primary_market_prices(request):
    # Get distinct scripts from the Purchase model (Primary Market Only)
    scripts = Purchase.objects.filter(mode='new-issue').values_list('script', flat=True).distinct()

    if request.method == "POST":
        form = PrimaryMarketPriceForm(request.POST, scripts=scripts)
        if form.is_valid():
            entry_date = form.cleaned_data['entry_date']
            
            # Loop through each script and save its price
            for script in scripts:
                price_field = f"price_{script}"
                price = form.cleaned_data.get(price_field)

                # Save PrimaryMarketPrice entry
                PrimaryMarketPrice.objects.create(
                    entry_date=entry_date,
                    script=script,
                    price=price,
                )
            
            return redirect('primary-market-price-success')  # Redirect to success page or home
    else:
        form = PrimaryMarketPriceForm(scripts=scripts)

    return render(request, 'add_primary_market_prices.html', {'form': form})
'''
def purchase_summary(request):
    # Fetch date range from request GET parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Convert to proper date objects if provided
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")

    # Fetch all purchases with mode 'new-issue'
    all_purchases = Purchase.objects.filter(mode='new-issue')

    # Step 1: Annotate each row with 'line_total' as qty * purchase_rate
    annotated_purchases = all_purchases.annotate(
        line_total=F('qty') * F('purchase_rate')
    )

    # Step 2: Aggregate totals using the annotated field
    purchases = (
        annotated_purchases.values('script')
        .annotate(
            purchase_date=Max('purchase_date'),
            purchase_rate=Max('purchase_rate'),
            total_qty=Sum('qty'),
            total_amount=Sum('line_total', output_field=DecimalField()),  # Sum the annotated field
        )
    )

    # Fetch listing prices
    scripts = [p['script'] for p in purchases]
    primary_prices = PrimaryMarketPrice.objects.filter(script__in=scripts)

    # Filter for date range
    if start_date and end_date:
        primary_prices = primary_prices.filter(entry_date__range=(start_date, end_date))

    # Get listing prices
    listing_prices = {
        price.script: price.price
        for price in primary_prices.filter(listing=True)
    }

    # Get the latest prices per script for each month
    monthly_prices = (
        primary_prices.values('script', 'entry_date')
        .annotate(last_price=Max('price'))
        .order_by('script', 'entry_date')
    )

    # Prepare data for rendering
    data = []
    for purchase in purchases:
        script = purchase['script']
        listing_price = listing_prices.get(script)

        # Collect monthly prices and percentages
        script_prices = monthly_prices.filter(script=script)
        current_prices = [
            {
                'date': price['entry_date'],
                'percentage': ((price['last_price'] * 100 - purchase['purchase_rate']) / purchase['purchase_rate'])
                if price['last_price']
                else None,
            }
            for price in script_prices
        ]

        # Append purchase data
        data.append({
            'purchase_date': purchase['purchase_date'],
            'script': script,
            'total_qty': purchase['total_qty'],
            'purchase_rate': purchase['purchase_rate'],
            'total_amount': purchase['total_amount'],
            'listing_price': listing_price,
            'listing_percentage': ((listing_price - purchase['purchase_rate'])/ purchase['purchase_rate']) * 100 if listing_price else None,
            'current_prices': current_prices,
        })

    return render(request, 'purchase_summary.html', {'data': data, 'start_date': start_date, 'end_date': end_date})
'''
def purchase_summary(request):
    # Fetch the selected month from request GET parameters
    selected_month = request.GET.get('selected_month')
    today = datetime.today()

    # Calculate the start of the last 12 months
    twelve_months_ago = today.replace(day=1) - timedelta(days=365)

    # Default to the most recent month if none selected
    if selected_month:
        selected_month_date = datetime.strptime(selected_month, "%Y-%m")
    else:
        selected_month_date = today.replace(day=1) - timedelta(days=today.day)  # Previous month

    # Fetch all purchases with mode 'new-issue'
    all_purchases = Purchase.objects.filter(mode='new-issue')

    # Annotate each row with 'line_total'
    annotated_purchases = all_purchases.annotate(
        line_total=F('qty') * F('purchase_rate')
    )

    # Aggregate totals for the main table
    purchases = (
        annotated_purchases.values('script')
        .annotate(
            purchase_date=Max('purchase_date'),
            purchase_rate=Max('purchase_rate'),
            total_amount=Sum('line_total'),
        )
    )

    # Fetch quantities from the Balance table
    balance_data = Balance.objects.values('script').annotate(total_qty=Sum('qty'))
    balance_qty_map = {item['script']: item['total_qty'] for item in balance_data}

    # Update purchase data with quantities from Balance
    for purchase in purchases:
        purchase['total_qty'] = balance_qty_map.get(purchase['script'], 0)

    # Fetch all prices (remove 'listing=True' filter)
    scripts = [p['script'] for p in purchases]
    all_prices = PrimaryMarketPrice.objects.filter(script__in=scripts)

    # Filter for last 12 months prices
    last_12_months_prices = all_prices.filter(entry_date__gte=twelve_months_ago)

    # Get the last entry per month for the past 12 months
    monthly_prices = (
        last_12_months_prices.values('script')
        .annotate(month=F('entry_date__month'), year=F('entry_date__year'))
        .annotate(last_price=Max('price'))
        .order_by('script', 'year', 'month')
    )

    # Filter for the selected month
    selected_month_prices = all_prices.filter(
        entry_date__year=selected_month_date.year, entry_date__month=selected_month_date.month
    )

    # Fetch listing prices (keep 'listing=True' only for this case)
    listing_prices = all_prices.filter(listing=True)
    listing_price_dict = {price.script: price.price for price in listing_prices}

    # Prepare data for rendering
    last_12_months_data = []
    total_amount_total = 0
    listing_amount_total = 0
    current_amount_total = 0
    for purchase in purchases:
        script = purchase['script']

        # Get the listing price for the script
        listing_price = listing_price_dict.get(script)
        total_qty = purchase['total_qty']

        # Calculate listing amount
        listing_amount = listing_price * total_qty if listing_price else 0

        # Collect monthly prices
        script_prices = monthly_prices.filter(script=script)
        monthly_data = []
        last_price = None
        for price in script_prices:
            last_price = price['last_price']
            purchase_rate = purchase['purchase_rate']

            # Calculate current total amount
            current_total_amount = last_price * total_qty if last_price else 0  
            
            # Calculate totals for this script
            total_amount_total += purchase['total_amount']
            listing_amount_total += listing_amount
            current_amount_total += current_total_amount
        
            # Calculate percentages
            price_percentage = ((last_price - purchase_rate) / purchase_rate * 100) if last_price else None
            listing_price_percentage = ((listing_price - purchase_rate) / purchase_rate * 100) if listing_price else None

            monthly_data.append({
                'month': f"{price['year']}-{price['month']:02}",
                'last_price': last_price,
                'price_percentage': price_percentage,
                'listing_price_percentage': listing_price_percentage,
                'current_total_amount': current_total_amount,
            })

        # Append purchase data
        last_12_months_data.append({
            'purchase_date': purchase['purchase_date'],
            'script': script,
            'total_qty': purchase['total_qty'],
            'purchase_rate': purchase['purchase_rate'],
            'total_amount': purchase['total_amount'],
            'listing_price': listing_price,
            'listing_amount': listing_amount,
            'listing_price_percentage': listing_price_percentage,
            'monthly_data': monthly_data,
        })

    # Prepare selected month details
    selected_month_data = []
    for price in selected_month_prices:
        script = price.script
        purchase = next((p for p in purchases if p['script'] == script), None)

        if purchase:
            total_qty = purchase['total_qty']
            purchase_rate = purchase['purchase_rate']
            total_amount = total_qty * purchase_rate if total_qty else 0
            listing_price = listing_price_dict.get(script)
            listing_amount = listing_price * total_qty if listing_price else 0
            
            price_percentage = ((price.price - purchase_rate) / purchase_rate * 100) if price.price else None
            listing_price_percentage = ((listing_price_dict.get(script, 0) - purchase_rate) / purchase_rate * 100) if listing_price_dict.get(script, 0) else None

            selected_month_data.append({
                'script': script,
                'entry_date': price.entry_date,
                'price': price.price,
                'price_percentage': price_percentage,
                'listing_price_percentage': listing_price_percentage,
                'total_qty': total_qty,
                'purchase_rate': purchase_rate,
                'total_amount': total_amount,
                'listing_price': listing_price,
                'listing_amount': listing_amount,
            })
    # Sort selected month data by script name
    selected_month_data.sort(key=lambda x: (x['script'], x['entry_date']))
    
     # Calculate price percentage total
    price_percentage_total = (
        (current_amount_total - total_amount_total) * 100 / total_amount_total
        if total_amount_total > 0 else 0
    )

    return render(request, 'purchase_summary.html', {
        'last_12_months_data': last_12_months_data,
        'selected_month_data': selected_month_data,
        'total_amount_total': total_amount_total,
        'listing_amount_total': listing_amount_total,
        'current_amount_total': current_amount_total,
        'months': [
            (today.replace(day=1) - timedelta(days=30 * i)).strftime('%Y-%m')
            for i in range(12)
        ],
        'selected_month': selected_month_date.strftime('%Y-%m'),
    })




def loan_list(request):
    loans = Loan.objects.prefetch_related('payments', 'principal_payments')
    loan_data = []

    # Define the financial year dates
    today = date.today()
    if today.month < 4:  # If the current date is before April, we are in the previous financial year
        current_financial_year_start = date(today.year - 1, 4, 1)
        current_financial_year_end = date(today.year, 3, 31)
    else:  # Otherwise, we are in the current financial year
        current_financial_year_start = date(today.year, 4, 1)
        current_financial_year_end = date(today.year + 1, 3, 31)

    for loan in loans:
        

        # Calculate total amount paid for the current financial year
        current_year_payments = loan.payments.filter(paymentDate__range=(current_financial_year_start, current_financial_year_end))
        total_amount_paid_current_year = current_year_payments.aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Calculate total amount paid across all years
        total_amount_paid_all_years = loan.payments.aggregate(Sum('amount'))['amount__sum'] or 0

        total_principal_paid = loan.principal_payments.aggregate(Sum('givenAmount'))['givenAmount__sum'] or 0
        
        # Calculate the remaining balance
        remaining_balance = loan.principleAmount - total_principal_paid
        
        # Calculate repayment progress percentage
        repayment_progress = min((total_principal_paid / loan.principleAmount) * 100, 100) if loan.principleAmount > 0 else 0
        
        # Group and sum payments for previous financial years
        previous_year_payments = loan.payments.filter(paymentDate__lt=current_financial_year_start)
        previous_year_summary = (
            previous_year_payments
            .annotate(financial_year=ExtractYear('paymentDate'))
            .values('financial_year')
            .annotate(total_paid=Sum('amount'))
            .order_by('financial_year')
        )

        principal_payments = (
    loan.principal_payments.annotate(
        cumulative_given=Window(
            expression=Sum('givenAmount'),
            order_by=F('paymentDate').asc()
        ),
        remaining_balance=F('loan__principleAmount') - Coalesce(Window(
            expression=Sum('givenAmount'),
            order_by=F('paymentDate').asc()
        ), 0, output_field=DecimalField()),
    )
)
       
        
        loan_data.append({
            'loan': loan,
            
            'total_amount_paid_current_year': total_amount_paid_current_year,
            'total_amount_paid_all_years': total_amount_paid_all_years,
            'current_year_payments': current_year_payments,
            'previous_year_summary': previous_year_summary,
            'total_principal_paid': total_principal_paid,
            'remaining_balance': remaining_balance,
            'repayment_progress': repayment_progress,
            'principal_payments': principal_payments,
            
        })

    context = {'loan_data': loan_data}
    return render(request, 'loan_list.html', context)


def new_loan(request):
    if request.method == 'POST':
        form = LoanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('loan_list')
    else:
        form = LoanForm()
    return render(request, 'loan_form.html', {'form': form})


def new_payment(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.loan = loan
            payment.save()
            return redirect('loan_list')
    else:
        form = PaymentForm()
    return render(request, 'payment_form.html', {'form': form, 'loan': loan})

def new_principal_payment(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)
    if request.method == 'POST':
        form = PrincipalPaymentForm(request.POST)
        if form.is_valid():
            principal_payment = form.save(commit=False)
            principal_payment.loan = loan
            principal_payment.save()
            return redirect('loan_list')
    else:
        form = PrincipalPaymentForm()
    return render(request, 'principal_payment_form.html', {'form': form, 'loan': loan})



def calculate_payment_dates_and_amounts(payment):
    loan_id = payment.loan
    payment_date = payment.paymentDate
    amount = payment.amount + loan_id.remainingBalance
    
    print(f"Initial payment: amount={amount}, loan_id={payment.loan.loanId}")

    # Get last payment's endDate for the same loanID
    last_payment = Payment.objects.filter(loan=loan_id).exclude(id=payment.id).order_by('-endDate').first()
    if last_payment:
        start_date = last_payment.endDate + timedelta(days=1)
    else:
        # First record for this loanID, startDate = loanDate
        start_date = loan_id.loanDate

    payment.startDate = start_date

    # Iterate through PrincipalPayment ranges
    remaining_amount = amount
    current_start_date = start_date

    while remaining_amount > 0:
        # Find the correct range for the current start_date
        principal_range = PrincipalPayment.objects.filter(
            loan=loan_id, paymentDate__lte=current_start_date
        ).order_by('-paymentDate').first()

        if not principal_range:
            break  # No more ranges

        per_day_value = principal_range.prinInterestMonth / 30
        days_for_amount = int(remaining_amount / per_day_value)
        temp_end_date = current_start_date + timedelta(days=days_for_amount)
        print("Per day value: ",per_day_value)
        print("Days in range: ",days_for_amount)
        print("expected end date : ",temp_end_date)
        
        # Now, find the next record for the loan (after the current principal_range's paymentDate)
        next_principal_range = PrincipalPayment.objects.filter(
            loan=loan_id, paymentDate__gt=principal_range.paymentDate
        ).order_by('paymentDate').first()

        if next_principal_range:
           
            # Check if temp_end_date exceeds current range's paymentDate
            if temp_end_date > next_principal_range.paymentDate:
                temp_end_date = next_principal_range.paymentDate
            print(f"Next principal range found with paymentDate: {principal_range.paymentDate}")
        else:
            # No next record found, break the loop
            print("No next principal range found. Ending the iteration.")
            
        print("End Date selected",temp_end_date)
        
        
            
        
        

        days_between = (temp_end_date - current_start_date).days
        new_amount = per_day_value * days_between
        print("New amount: ",new_amount)
        
        # Prevent infinite loop if new_amount is too small
        if new_amount < per_day_value:  # Set an appropriate threshold to prevent a very small payment from looping
            print(f"New amount is too small to progress: {new_amount}")
            loan_id.remainingBalance = remaining_amount  # Store the remaining small balance on the loan
            loan_id.save()
            break

        # Update payment fields for this iteration
        # Create and save a new Payment record
        new_payment = Payment(
            loan=loan_id,
            paymentDate=payment_date,
            amount=new_amount,
            granter=payment.granter,
            recipient=payment.recipient,
            site=payment.site,
            startDate=current_start_date,
            endDate=temp_end_date,
        )
        new_payment._saved = True  # Mark as saved to prevent recursive calls
        new_payment.save()
        
        
        
        
        

        # Adjust remaining amount and current_start_date
        remaining_amount -= new_amount
        if remaining_amount <= 0:
            break 
        current_start_date = temp_end_date + timedelta(days=1)
      
def client_specific_analysis(request):
     ''' 
    client_name = 'Sanghavi'  # Hardcoded client name (you can also pass this dynamically)
    client = Client.objects.get(clientName=client_name)
    
    # 1. Loan Participation Overview
    lender_loans = Loan.objects.filter(lender=client)
    borrower_loans = Loan.objects.filter(borrower=client)
    total_lender_loans = lender_loans.count()
    total_borrower_loans = borrower_loans.count()

    # 2. Payment Flow (Sankey diagram data)
    total_sent = Payment.objects.filter(granter=client).aggregate(Sum('amount'))['amount__sum'] or 0
    total_received = Payment.objects.filter(recipient=client).aggregate(Sum('amount'))['amount__sum'] or 0

    # 3. Total Outstanding Loans (for client as a borrower)
    outstanding_loans = borrower_loans.filter(status=True)
    total_outstanding_balance = outstanding_loans.aggregate(Sum('remainingBalance'))['remainingBalance__sum'] or 0

    # 4. Revenue (Interest Earned for lender)
    interest_earned = lender_loans.aggregate(Sum('interestMonth'))['interestMonth__sum'] or 0

    # 5. Top Borrowers/Lenders Analysis
    top_borrowers = Loan.objects.values('borrower').annotate(total_principal=Sum('principleAmount')).order_by('-total_principal')[:5]
    top_lenders = Loan.objects.values('lender').annotate(total_principal=Sum('principleAmount')).order_by('-total_principal')[:5]

    # 6. Revenue vs Payments (Net profit analysis for the client)
    net_profit = total_received - total_sent

    # 7. Average Loan Size
    average_loan_size = Loan.objects.filter(Q(lender=client) | Q(borrower=client)).aggregate(Sum('principleAmount'))['principleAmount__sum'] / (total_lender_loans + total_borrower_loans) if (total_lender_loans + total_borrower_loans) > 0 else 0

    # 8. Risk Exposure (for lenders)
    risk_exposure = lender_loans.aggregate(Sum('remainingBalance'))['remainingBalance__sum'] or 0

    # Visualization for Loan Participation Overview
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(['Lender', 'Borrower'], [total_lender_loans, total_borrower_loans], color=['blue', 'green'])
    ax.set_title('Loan Participation Overview')
    ax.set_ylabel('Number of Loans')
    ax.set_xlabel('Client Role')
    fig.tight_layout()
    
    # Save chart to base64 to embed it in the template
    chart_io = io.BytesIO()
    plt.savefig(chart_io, format='png')
    chart_io.seek(0)
    chart_data = base64.b64encode(chart_io.getvalue()).decode('utf-8')
    plt.close(fig)

    context = {
        'client': client,
        'total_lender_loans': total_lender_loans,
        'total_borrower_loans': total_borrower_loans,
        'total_sent': total_sent,
        'total_received': total_received,
        'total_outstanding_balance': total_outstanding_balance,
        'interest_earned': interest_earned,
        'top_borrowers': top_borrowers,
        'top_lenders': top_lenders,
        'net_profit': net_profit,
        'average_loan_size': average_loan_size,
        'risk_exposure': risk_exposure,
        'chart_data': chart_data,
    }

    return render(request, 'client_analysis.html', context)
'''