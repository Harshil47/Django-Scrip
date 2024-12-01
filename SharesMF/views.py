from django.shortcuts import render , redirect , get_object_or_404
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from .models import Purchase, UserTable , Balance , Sale , TaxRate , Exemption, Broker , StockPrice
import json , requests
from django.db.models import Sum , Q  , F, ExpressionWrapper, DecimalField, Value, Case, When , FloatField , Count
from django.contrib import messages
from datetime import datetime , timedelta 
from decimal import Decimal
from django.contrib import messages 



class PurchaseEntryView(View):
    
    def post(self, request):
        # Create a new purchase entry
        try:
            data = json.loads(request.body)
            print("POST request received")
            
            # Retrieve the user object using the name field
            user = UserTable.objects.get(name=data['user_name'])  # Use 'name' as the primary key
            broker = Broker.objects.get(name=data['broker']) if data.get('broker') else None
            mehul_value = data.get('mehul', False)
            entry_value = data.get('entry', '')
            print("Received data:", data)
            print("User retrieved:", user)
            # Create and save the purchase entry
            purchase = Purchase.objects.create(
                purchase_date=data['purchase_date'],
                script=data['script'],
                type=data['type'],
                user=user,  # Associate the user using the user object
                qty=data['qty'],
                purchase_rate=data['purchase_rate'],
                broker=broker,
                mode=data['mode'],
                mehul=mehul_value,
                entry=entry_value
            )
            purchase.save()
            print("Purchase saved:", purchase)
            return JsonResponse(model_to_dict(purchase), status=201)
        except UserTable.DoesNotExist:
            print("Error: User with the given name not found")
            return JsonResponse({'error': 'User with the given name not found'}, status=400)
        except Broker.DoesNotExist:
            return JsonResponse({'error': 'Broker not found'}, status=400)
        except Exception as e:
            
            return JsonResponse({'error': str(e)}, status=400)

def purchase_view(request):
    return render(request, 'purchase.html')


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
    # Fetch the exemption amount from the Exemption table
    try:
        exemption = Exemption.objects.get(long='longTerm') 
        exemption_amount = Decimal(exemption.deduct)
    except Exemption.DoesNotExist:
        exemption_amount = Decimal(0)  # Default to 0 if no exemption record is found

    # Update the long-term tax calculation logic
    taxable_long_term_profit = max(Decimal(0), long_term_profit - long_term_loss - exemption_amount)
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
