from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

# Create your models here.


# Profile model
class Profile(models.Model):
    user_id = models.OneToOneField(User,on_delete=models.CASCADE)

    phone = models.CharField(max_length=15)

    profile_image = models.ImageField(upload_to="profiles/",blank=False,null=False)

    age = models.IntegerField(blank=False,null=False)
    
    gender=models.CharField(max_length=10,blank=False,null=False)

    def __str__(self):
        return self.user_id.username
    
    

#  plan model
class PlanModel(models.Model):
    MONTHLY_BOOKING_LIMIT = 8
    CUSTOM_BOOKING_LIMIT = 8

    PLAN_CHOICES = [
        ("basic", "Basic"),
        ("monthly", "Monthly"),
        ("custom", "Custom"),
    ]
    WEEKDAY_CHOICES = [
        ("0", "Monday"),
        ("1", "Tuesday"),
        ("2", "Wednesday"),
        ("3", "Thursday"),
        ("4", "Friday"),
        ("5", "Saturday"),
        ("6", "Sunday"),
    ]
    
    TIME_SLOT_CHOICES = [
    ("09:00", "09:00 AM - 10:00 AM"),
    ("10:00", "10:00 AM - 11:00 AM"),
    ("11:00", "11:00 AM - 12:00 PM"),
    ("12:00", "12:00 PM - 01:00 PM"),
    ("13:00", "01:00 PM - 02:00 PM"),
    ("14:00", "02:00 PM - 03:00 PM"),
    ("15:00", "03:00 PM - 04:00 PM"),
    ("16:00", "04:00 PM - 05:00 PM"),
    ("17:00", "05:00 PM - 06:00 PM"),
    ("18:00", "06:00 PM - 07:00 PM"),
    ("19:00", "07:00 PM - 08:00 PM"),
    ("20:00", "08:00 PM - 09:00 PM"),
    ("21:00", "09:00 PM - 10:00 PM"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="choseplans")
    
    booking = models.ForeignKey(
    "Booking",
    on_delete=models.CASCADE,
    related_name="slots",
    null=True,
    blank=True,
)
    plan = models.CharField(
        max_length=10,
        choices=PLAN_CHOICES
        
    )
    
    time_Slot=models.CharField(max_length=5, choices=TIME_SLOT_CHOICES,null=False)
    date=models.DateField(null=False)
    
    price=models.DecimalField(max_digits=8,decimal_places=2)
    
    username=models.CharField(max_length=100)
    
    booking_date = models.DateField(default=timezone.localdate)
    
    
    # validation to check 5 user are booked or not
    MAX_USERS_PER_SLOT = 5

    def clean(self):
        super().clean()

        if self.date and self.time_Slot:
            bookings = PlanModel.objects.filter(
                date=self.date,
                time_Slot=self.time_Slot,
            )

            # Existing record update karte waqt khud ko count mat karo
            if self.pk:
                bookings = bookings.exclude(pk=self.pk)

            if bookings.count() >= self.MAX_USERS_PER_SLOT:
                raise ValidationError({
                    "time_Slot": (
                        "This time slot is fully booked. "
                        "Maximum 5 users can book this slot per day."
                    )
                })
    
    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.time_Slot}"
    


# booking detail model
class Booking(models.Model):
    BOOKING_STATUS_CHOICES = [
    ("pending", "Pending Payment"),
    ("success", "Success"),
    ("rejected", "Rejected"),
    ("canceled", "Canceled"),
]

    PLAN_CHOICES = [
        ("basic", "Basic"),
        ("monthly", "Monthly"),
        ("custom", "Custom"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="booking_records",
    )
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES)
    booking_status = models.CharField(
        max_length=20,
        choices=BOOKING_STATUS_CHOICES,
        default="success",
    )
    username = models.CharField(max_length=100)
    weekdays = models.CharField(max_length=100, blank=True)
    slot_time = models.CharField(max_length=50)
    start_date = models.CharField(max_length=100)
    end_date = models.CharField(max_length=100, blank=True, null=True)
    selected_dates = models.TextField(blank=True)
    holiday_shifted_count = models.PositiveSmallIntegerField(default=0)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    payment_status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} - {self.plan}"
    


# payment detail model
class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="payment",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=3,
        default="INR",
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending",
    )

    razorpay_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for Booking #{self.booking_id}"
