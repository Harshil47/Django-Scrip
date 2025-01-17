from django import forms 
from .models import PrimaryMarketPrice , Loan , Payment, PrincipalPayment
class StockSplitForm(forms.Form):
    script = forms.CharField(max_length=100)
    split_date = forms.DateField(widget=forms.SelectDateWidget)
    ratio = forms.FloatField(min_value=1.0)
    
class BonusForm(forms.Form):
    script = forms.CharField(widget=forms.HiddenInput())
    bonus_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    ratio = forms.IntegerField(min_value=1, label="Bonus Ratio (e.g., 2 for 1:2)")

class PrimaryMarketPriceForm(forms.Form):
    entry_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}), 
        label="Entry Date"
    )

    def __init__(self, *args, **kwargs):
        scripts = kwargs.pop('scripts', [])  # Pass distinct scripts to the form
        super().__init__(*args, **kwargs)

        # Dynamically create fields for each script
        for script in scripts:
            self.fields[f"price_{script}"] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                label=f"Price for {script}",
                required=True,
            )

class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['lender', 'borrower', 'principleAmount', 'loanDate', 'percentMonth', 'status']
        widgets = {
            'loanDate': forms.DateInput(attrs={'type': 'date'}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['paymentDate', 'amount', 'granter', 'recipient', 'site']
        widgets = {
            'paymentDate': forms.DateInput(attrs={'type': 'date'}),
        }

class PrincipalPaymentForm(forms.ModelForm):
    class Meta:
        model = PrincipalPayment
        fields = ['paymentDate', 'givenAmount']