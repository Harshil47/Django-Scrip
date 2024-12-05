from django.db import models
from django.contrib.auth.models import User
from datetime import date, timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal , InvalidOperation
import traceback

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
    # New boolean field for 'mehul'
    mehul = models.BooleanField(default=False)  # Default to "No"
    entry = models.CharField(max_length=255, null=True, blank=True)
    referenced_by = models.CharField(max_length=100, null=True, blank=True) 


    def save(self, *args, **kwargs):
        self.purchase_amount = self.qty * self.purchase_rate
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
        print(f"DEBUG: Sale Qty - Qty={self.qty}, Amount={self.amount}")
        if self.qty and self.rate:
            self.amount = self.qty * self.rate
            
        
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