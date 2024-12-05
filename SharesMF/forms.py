from django import forms

class StockSplitForm(forms.Form):
    script = forms.CharField(max_length=100)
    split_date = forms.DateField(widget=forms.SelectDateWidget)
    ratio = forms.FloatField(min_value=1.0)