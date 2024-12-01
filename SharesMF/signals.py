from django.db.models.signals import post_save , post_delete
from django.dispatch import receiver
from .models import Purchase, Balance , Sale
from decimal import Decimal 
from django.db import transaction
from django.core.exceptions import ValidationError
@receiver(post_save, sender=Purchase)
def create_balance_entry(sender, instance, created, **kwargs):
    if created:  # Only create a Balance entry for new purchases
        Balance.objects.create(
            purchase_id=instance,
            script=instance.script,
            type=instance.type,
            user=instance.user,
            qty=instance.qty,
            rate=instance.purchase_rate,
            amount=instance.purchase_amount,
        )
        
@receiver(post_save, sender=Sale)
def update_balance_after_sale(sender, instance, created, **kwargs):
    if created:  # Ensure this runs only when a Sale is created, not updated
        # Find the corresponding balance entry
        balance_entry = Balance.objects.filter(
            purchase_id=instance.purchase_id,
            script=instance.script,
            user=instance.user
        ).first()

        if balance_entry:
            print(f"DEBUG: Found balance entry: Qty={balance_entry.qty}, Rate={balance_entry.rate}, Amount={balance_entry.amount}")
            new_qty = balance_entry.qty - instance.qty
            print(f"DEBUG: New Qty = {new_qty} (Old Qty={balance_entry.qty} - Sale Qty={instance.qty})")
            new_amount = Decimal(new_qty) * balance_entry.rate
            print(f"DEBUG: New Amount = {new_amount} (New Qty={new_qty} * Rate={balance_entry.rate})")

            if new_qty <= 0:
                print(f"DEBUG: Deleting balance entry because New Qty <= 0")
                # Use atomic block to ensure the delete is committed correctly
                try:
                    with transaction.atomic():  # Ensure deletion is committed
                        balance_entry.delete()
                        print(f"DEBUG: Balance entry deleted successfully")
                except Exception as e:
                    print(f"ERROR: Unable to delete balance entry - {e}")
            else:
                # Update balance entry with the new qty and amount
                balance_entry.qty = new_qty
                balance_entry.amount = new_amount
                balance_entry.save()
                print(f"DEBUG: Updated Balance Entry: Qty={balance_entry.qty}, Amount={balance_entry.amount}")
        


@receiver(post_delete, sender=Purchase)
def handle_purchase_deletion(sender, instance, **kwargs):
    """
    Handle updates to the Balance table when a Purchase record is deleted.
    """
    # Find the corresponding balance entry
    balance_entry = Balance.objects.filter(
        purchase_id=instance,
        script=instance.script,
        user=instance.user
    ).first()

    if balance_entry:
        if balance_entry.qty == instance.qty:  # Quantity matches
            balance_entry.delete()
        else:
            raise ValidationError(
                f"Cannot delete Purchase ID {instance.purchase_id}. "
                f"Balance table quantity ({balance_entry.qty}) does not match Purchase quantity ({instance.qty})."
            )
            
@receiver(post_delete, sender=Sale)
def handle_sale_deletion(sender, instance, **kwargs):
    """
    Update the Balance table when a Sale record is deleted.
    """
    try:
        # Fetch the corresponding Balance entry
        balance_entry = Balance.objects.filter(
            purchase_id=instance.purchase_id,
            script=instance.script,
            user=instance.user
        ).first()

        if balance_entry:
            # Case 1: Update the existing Balance entry
            new_qty = balance_entry.qty + instance.qty
            new_amount = Decimal(new_qty) * balance_entry.rate
            
            print(f"DEBUG: Updating Balance Entry - New Qty={new_qty}, New Amount={new_amount}")
            
            # Update the balance record
            balance_entry.qty = new_qty
            balance_entry.amount = new_amount
            balance_entry.save()
        else:
            # Case 2: Create a new Balance entry
            purchase_record = instance.purchase_id  # Fetch the associated Purchase record
            new_amount = Decimal(instance.qty) * purchase_record.purchase_rate

            print(f"DEBUG: Creating new Balance Entry - Qty={instance.qty}, Rate={purchase_record.purchase_rate}, Amount={new_amount}")
            
            # Create a new balance record
            Balance.objects.create(
                purchase_id=purchase_record,
                script=instance.script,
                type=purchase_record.type,
                user=instance.user,
                qty=instance.qty,
                rate=purchase_record.purchase_rate,
                amount=new_amount,
            )
    except Exception as e:
        print(f"ERROR: Failed to update Balance table on Sale deletion - {e}")