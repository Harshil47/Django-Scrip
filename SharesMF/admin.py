
from django.contrib import admin
from .models import UserTable, Purchase, Balance, Sale , TaxRate , Exemption , Broker

admin.site.register(UserTable)
admin.site.register(Purchase)
admin.site.register(Balance)
admin.site.register(Sale)
admin.site.register(TaxRate)
admin.site.register(Exemption)
admin.site.register(Broker)
