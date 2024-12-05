from django.shortcuts import render , redirect , get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from .models import Purchase, UserTable , Balance , Sale , TaxRate , Exemption, Broker , StockPrice , StockSplit
from .forms import StockSplitForm
import json , requests
from django.db.models import Sum , Q  , F, ExpressionWrapper, DecimalField, Value, Case, When , FloatField , Count
from django.contrib import messages
from datetime import datetime , timedelta 
from decimal import Decimal
from django.contrib import messages 
from django.db import transaction, models
import traceback


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
