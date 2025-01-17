
from django.contrib import admin
from .models import UserTable, Purchase, Balance, Sale , TaxRate , Exemption , Broker , StockSplit , Adjustment , PrimaryMarketPrice, ScriptINE, Loan, Payment,Client, PrincipalPayment

admin.site.register(UserTable)
admin.site.register(Purchase)
admin.site.register(Balance)
admin.site.register(Sale)
admin.site.register(TaxRate)
admin.site.register(Exemption)
admin.site.register(Broker)
admin.site.register(StockSplit)
admin.site.register(Adjustment)
admin.site.register(PrimaryMarketPrice)
admin.site.register(ScriptINE)
admin.site.register(Client)
admin.site.register(Loan)
admin.site.register(Payment)
admin.site.register(PrincipalPayment)