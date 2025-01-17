# Generated by Django 4.2.16 on 2025-01-15 21:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SharesMF', '0025_payment_enddate_payment_startdate'),
    ]

    operations = [
        migrations.AddField(
            model_name='loan',
            name='remainingBalance',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12),
        ),
    ]
