from django.db import models
from django.contrib.auth.models import User
from datetime import date, timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal , InvalidOperation
import traceback
from django.db.models import Sum, Avg, Max , F
from collections import defaultdict




class UserTable(models.Model):
    name = models.CharField(max_length=100, primary_key=True)
    pan = models.CharField(max_length=20, unique=True)
    family = models.CharField(max_length=100, null=True, blank=True)
    data_entry = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    
class Broker(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name



class Purchase(models.Model):
    purchase_id = models.AutoField(primary_key=True)
    purchase_date = models.DateField()
    script = models.CharField(max_length=100)
    TYPE_CHOICES = [
        ('Share', 'Share'),
        ('MF', 'Mutual Fund'),
    ]
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    # Mode choices
    MODE_CHOICES = [
        ('secondary-market', 'Secondary Market'),
        ('new-issue', 'New Issue'),
    ]
    mode = models.CharField(
        max_length=20, 
        choices=MODE_CHOICES, 
        null=True,  # Allow null values
        blank=True  # Allow blank input in forms
    )
    user = models.ForeignKey(UserTable, to_field='name', on_delete=models.CASCADE)  # Use 'name' as the primary key
    qty = models.PositiveIntegerField()
    purchase_rate = models.DecimalField(max_digits=25, decimal_places=2)
    purchase_amount = models.DecimalField(max_digits=25, decimal_places=2, blank=True)
    broker = models.ForeignKey(Broker, on_delete=models.SET_NULL, null=True, blank=True)
    mehul = models.BooleanField(default=False)  # Default to "No"
    entry = models.CharField(max_length=255, null=True, blank=True)
    referenced_by = models.CharField(max_length=100, null=True, blank=True)
    

    def save(self, *args, **kwargs):
        # Calculate the base purchase amount
        base_amount = self.qty * self.purchase_rate

        # Fetch the total adjustment
        total_adjustment = Adjustment.objects.filter(purchase_id=self).aggregate(
            total_adjustment=models.Sum('adjustment_value')
        )['total_adjustment'] or 0

        # Set purchase_amount to include adjustments
        self.purchase_amount = base_amount + total_adjustment

        # Optionally, print debug information
        print(f"DEBUG: Saving Purchase ID {self.purchase_id}: base_amount={base_amount}, "
              f"total_adjustment={total_adjustment}, purchase_amount={self.purchase_amount}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.purchase_id}"



class Balance(models.Model):
    purchase_id = models.ForeignKey(Purchase, on_delete=models.CASCADE)
    script = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=Purchase.TYPE_CHOICES)
    user = models.ForeignKey(UserTable, to_field='name', on_delete=models.CASCADE) 
    qty = models.PositiveIntegerField()
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    def save(self, *args, **kwargs):
        # Calculate the base amount
        base_amount = self.qty * self.rate

        # Fetch total adjustments for the associated purchase
        total_adjustment = Adjustment.objects.filter(purchase_id=self.purchase_id).aggregate(
            total_adjustment=models.Sum('adjustment_value')
        )['total_adjustment'] or 0

        # Include adjustments in the amount calculation
        self.amount = base_amount + total_adjustment

        # Debugging information
        print(f"DEBUG: Saving Balance for {self.script} (Purchase ID {self.purchase_id}): "
              f"Base Amount={base_amount}, Total Adjustment={total_adjustment}, Final Amount={self.amount}")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.script} Balance for {self.user.name}"


class Sale(models.Model):
    sale_date = models.DateField()
    purchase_id = models.ForeignKey(Purchase, on_delete=models.CASCADE)
    script = models.CharField(max_length=100)
    user = models.ForeignKey(UserTable, to_field='name', on_delete=models.CASCADE)
    qty = models.PositiveIntegerField()
    sale_rate = models.DecimalField(max_digits=10, decimal_places=2)
    sale_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    gf_rate = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    short_profit = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    long_profit = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    short_loss = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    long_loss = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)  
    spec_profit = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True) 
    spec_loss = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)  
    
    def calculate_profit_loss(self, gf_rate=None):
        # Use user-provided GF rate if available, otherwise default to saved GF rate
        effective_gf_rate = Decimal(gf_rate) if gf_rate is not None else (self.gf_rate or Decimal(0))
        purchase_rate = self.purchase_id.purchase_rate or Decimal(0)
        effective_gf_rate = max(effective_gf_rate, purchase_rate)
        purchase_amount = (
            effective_gf_rate * self.qty
            if self.purchase_id.purchase_date < date(2018, 1, 31) and self.purchase_id.type == "Share"
            else self.purchase_id.purchase_rate * self.qty
        )

        # Convert sale_amount to Decimal
        sale_amount = Decimal(self.sale_amount)
        try:
            sale_amount = Decimal(self.sale_amount)
        except (InvalidOperation, ValueError):
            sale_amount = Decimal('0')  # Default to 0 if conversion fails
            print(f"Invalid sale_amount value: {self.sale_amount}, setting to 0.")
        date_diff = (self.sale_date - self.purchase_id.purchase_date).days

        if sale_amount > purchase_amount:
            self.short_loss = 0
            self.long_loss = 0
            self.spec_loss = 0
            self.short_profit = (sale_amount - purchase_amount) if date_diff <= 365 else 0
            self.long_profit = (sale_amount - purchase_amount) if date_diff > 365 else 0
            
            # Speculation logic for same-day trading (assuming 'sale_date' matches 'purchase_date')
            if self.sale_date == self.purchase_id.purchase_date:
                self.spec_profit = (sale_amount - purchase_amount) if sale_amount > purchase_amount else Decimal('0')
                #self.spec_loss = (purchase_amount - sale_amount) if sale_amount < purchase_amount else Decimal('0')
                self.short_profit = 0
                
            # Get tax rates from TaxRate table
            if self.short_profit > 0:
                tax_rate = TaxRate.objects.filter(profit='Short').first()  # Get the 'Short' tax rate
                if tax_rate:
                    self.tax = Decimal(self.short_profit) * Decimal(tax_rate.percent / 100)
            elif self.long_profit > 0:
                tax_rate = TaxRate.objects.filter(profit='Long').first()  # Get the 'Long' tax rate
                if tax_rate:
                    self.tax = Decimal(self.long_profit) * Decimal(tax_rate.percent / 100)
            elif self.spec_profit > 0:
                tax_rate = TaxRate.objects.filter(profit='Speculation').first()  # Get the 'Speculation' tax rate
                if tax_rate:
                    self.tax = Decimal(self.spec_profit) * Decimal(tax_rate.percent / 100)

        
        elif sale_amount < purchase_amount:
            self.short_profit = 0
            self.long_profit = 0
            self.spec_profit = 0
            self.short_loss = (purchase_amount - sale_amount) if date_diff <= 365 else 0
            self.long_loss = (purchase_amount - sale_amount) if date_diff > 365 else 0
            self.tax = Decimal('0') 
            self.spec_loss = Decimal('0')
            if self.sale_date == self.purchase_id.purchase_date:
                self.spec_loss = purchase_amount - sale_amount
                self.short_loss = 0
            
    def calculate_purchase_total(self):
        if self.purchase_id and self.purchase_id.purchase_rate:
            return self.purchase_id.purchase_rate * self.qty
        return None
    
    @property
    def short_net(self):
        return (self.short_profit or Decimal(0)) -(self.short_loss or Decimal(0)) - (self.tax or Decimal(0))

    @property
    def long_net(self):
        return (self.long_profit or Decimal(0)) -(self.long_loss or Decimal(0)) - (self.tax or Decimal(0))

    @property
    def spec_net(self):
        return (self.spec_profit or Decimal(0)) -(self.spec_loss or Decimal(0))- (self.tax or Decimal(0))
            
    def save(self, *args, **kwargs):
        self.sale_amount = self.qty * self.sale_rate
        self.calculate_profit_loss()
        
        

        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Sale of {self.script} by {self.user.name}"

class TaxRate(models.Model):
    profit = models.CharField(max_length=100)  
    percent = models.FloatField() 

    def __str__(self):
        return f"{self.profit} - {self.percent}%"
    
class Exemption(models.Model):
    long = models.CharField(max_length=100)  
    deduct = models.FloatField()  

    def __str__(self):
        return f"{self.long} - {self.deduct}"
    
class StockPrice(models.Model):
    script_name = models.CharField(max_length=50, unique=True)
    price = models.FloatField(null=False, default=0.0)
    last_updated = models.DateTimeField(auto_now=True)
    timeslot = models.TimeField()
    
class StockSplit(models.Model):
    script = models.CharField(max_length=100)
    split_date = models.DateField()
    ratio = models.FloatField()

    def __str__(self):
        return f"{self.script} - Split Ratio {self.ratio} on {self.split_date}"
    
class Bonus(models.Model):
    script = models.CharField(max_length=100)
    bonus_date = models.DateField()
    ratio = models.FloatField()

    def __str__(self):
        return f"{self.script} - Bonus Ratio {self.ratio} on {self.bonus_date}"

class Adjustment(models.Model):
    purchase_id = models.ForeignKey(Purchase, on_delete=models.CASCADE)
    adjustment_value = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"Adjustment for Purchase ID: {self.purchase_id}"
    
class PrimaryMarketPrice(models.Model):
    entry_date = models.DateField()  # Date of price entry
    script = models.CharField(max_length=100)  # Name of the share (script)
    price = models.DecimalField(max_digits=12, decimal_places=2)  # Current price
    listing = models.BooleanField(default=False)  

    def __str__(self):
        return f"{self.script} - {self.price} on {self.entry_date}"
    
class ScriptINE(models.Model):
    script = models.CharField(max_length=100, primary_key=True)  # Primary key to ensure uniqueness
    ine = models.CharField(max_length=50)
    
class Client(models.Model):
    clientName = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.clientName


class Loan(models.Model):
    STATUS_CHOICES = [
        (True, 'Active'),
        (False, 'Closed'),
    ]
    loanId = models.AutoField(primary_key=True)
    lender = models.ForeignKey(Client, related_name='loans_as_lender', on_delete=models.CASCADE)
    borrower = models.ForeignKey(Client, related_name='loans_as_borrower', on_delete=models.CASCADE)
    principleAmount = models.DecimalField(max_digits=12, decimal_places=2)
    loanDate = models.DateField()
    percentMonth = models.DecimalField(max_digits=5, decimal_places=2)
    interestMonth = models.DecimalField(max_digits=12, decimal_places=2, blank=True)
    status = models.BooleanField(choices=STATUS_CHOICES, default=True)
    remainingBalance = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True)  # New field

    def save(self, *args, **kwargs):
        self.interestMonth = self.principleAmount * self.percentMonth / 100
        super().save(*args, **kwargs)
        
        # Ensure a corresponding PrincipalPayment record exists
        if not PrincipalPayment.objects.filter(loan=self).exists():
            PrincipalPayment.objects.create(
                loan=self,
                paymentDate=self.loanDate,
                givenAmount=0,
                prinInterestMonth=self.interestMonth,  
            )

    def __str__(self):
        return f"Loan {self.loanId}"


class Payment(models.Model):
    loan = models.ForeignKey(Loan, related_name='payments', on_delete=models.CASCADE)
    paymentDate = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    granter = models.ForeignKey(Client, related_name='payments_as_granter', on_delete=models.CASCADE)
    recipient = models.ForeignKey(Client, related_name='payments_as_recipient', on_delete=models.CASCADE)
    site = models.CharField(max_length=255)
    startDate = models.DateField(null=True, blank=True)
    endDate = models.DateField(null=True, blank=True)
    _saved = False
    
    def save(self, *args, **kwargs):
    
        # Check if _saved flag is not set and perform calculations
        if not hasattr(self, '_saved') or not self._saved:
            from SharesMF.views import calculate_payment_dates_and_amounts
            # Perform calculations only the first time
            self._saved = True  # Mark as saved
            calculate_payment_dates_and_amounts(self)
            return
            
        
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment {self.id} for Loan {self.loan.loanId}"
    
class PrincipalPayment(models.Model):
    prinID = models.AutoField(primary_key=True)
    loan = models.ForeignKey(Loan, related_name='principal_payments', on_delete=models.CASCADE)
    paymentDate = models.DateField()
    givenAmount = models.DecimalField(max_digits=12, decimal_places=2)
    prinInterestMonth = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    def calculate_new_interest_month(self):
        total_principal_paid = PrincipalPayment.objects.filter(loan=self.loan).aggregate(Sum('givenAmount'))['givenAmount__sum'] or 0
        total_principal_paid += self.givenAmount
        remaining_principal = self.loan.principleAmount - total_principal_paid
        return remaining_principal * self.loan.percentMonth / 100

    def save(self, *args, **kwargs):
        self.prinInterestMonth = self.calculate_new_interest_month()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Principal Payment {self.prinID} for Loan {self.loan.loanId}"


