# Generated by Django 4.2.16 on 2024-11-21 03:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SharesMF', '0003_sale_spec_loss_sale_spec_profit'),
    ]

    operations = [
        migrations.CreateModel(
            name='Exemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('long', models.CharField(max_length=100)),
                ('deduct', models.FloatField()),
            ],
        ),
    ]
