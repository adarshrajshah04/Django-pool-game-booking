from datetime import timedelta,date
from decimal import Decimal
import logging
from django.contrib.auth.models import User

from django.shortcuts import render, redirect,get_object_or_404
from django.utils import timezone
from django.contrib.auth import login,decorators,authenticate
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from razorpay import Client as RazorpayClient

from razorpay.errors import (
    BadRequestError,
    GatewayError,
    ServerError,
    SignatureVerificationError,
)
from requests.exceptions import RequestException
from holidays import country_holidays
from .forms import PlanForm, RegistrationForm
from .models import Booking, Payment, PlanModel, Profile
from django.conf import settings

from django.contrib.auth.decorators import login_required


logger = logging.getLogger(__name__)

# Create your views here.

# resister view
def register(request):
    
    if request.method == "POST":
        email=request.POST.get("email")
        existUser=User.objects.filter(email=email)
        
        if existUser.exists():
            messages.error(request, "User already exists!")
            return redirect("/register/")
        
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(
                user_id=user,
                phone=request.POST.get("phone"),
                profile_image=request.FILES.get("profile_image"),
                age=request.POST.get("age"),
                gender=request.POST.get("gender"),
                
            )
            # Send welcome email
            send_mail(
                subject="Welcome to Game Booking!",
                message=f"""
                    Hi {user.username},

                    Welcome to our Game Booking website!

                    Your registration was successful.
                    Now you can explore games and book your favourite activities.

                    Thank you for joining us!

                    Regards,
                    Game Booking Team
                                    """,
                from_email=None,
                recipient_list=[user.email],
                fail_silently=False
            )
            
            return redirect("login")
    else:
        form = RegistrationForm()
    return render(request, "register.html", {"form": form})


# login view
def login_view(request):
    if request.method=="POST":
        
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("/dashboard/")
        else:
            messages.error(request, "Invalid username or password!")
        
    return render(request, "login.html", )

# layout view
def layout_view(request):
    user=request.user
    
    profile=Profile.objects.filter(user_id=user).first()
    

    context = {
            "user": user,
            "profile": profile,
        }
    return render(request,"layout.html",context)

# dashboard view
@decorators.login_required(login_url="login")
def dashboard_view(request):
    
    # Currently logged-in user
    user = request.user
    
    # print(user)
    
    profile = Profile.objects.filter(user_id=user).first()
    
    context = {
        "user": user,
        "profile": profile,
    }

    return render(request, "dashboard.html", context)


@decorators.login_required(login_url="login")
@require_GET
def dashboard_holidays(request):
    year_value = request.GET.get("year", "")
    try:
        year = int(year_value)
    except ValueError:
        return JsonResponse({"error": "A valid calendar year is required."}, status=400)

    if not 2001 <= year <= 2035:
        return JsonResponse(
            {"error": "Festival data is available for years 2001 through 2035."},
            status=400,
        )

    holidays = country_holidays("IN", years=[year])
    return JsonResponse({
        "year": year,
        "holidays": {
            holiday_date.isoformat(): name
            for holiday_date, name in sorted(holidays.items())
            if holiday_date.year == year
        },
    })




@login_required(login_url="login")
def selectPlan(request):
    if request.method == "POST":
        form = PlanForm(request.POST)

        if form.is_valid():
            current_user = request.user
            plan = form.cleaned_data["plan"]
            start_date = form.cleaned_data["date"]
            time_slot = form.cleaned_data["time_Slot"]
            weekdays = form.cleaned_data["weekdays"]  # list of weekday strings
            custom_dates = form.cleaned_data["custom_dates"]  # list of date objects for Custom

            today = timezone.localdate()
            holiday_cache = {}

            def holiday_name(selected_date):
                year = selected_date.year
                if year not in holiday_cache:
                    holiday_cache[year] = country_holidays("IN", years=[year])
                return holiday_cache[year].get(selected_date)

            booking_dates = []

            # BASIC: one selected date.
            if plan == "basic":
                if start_date:
                    booking_dates = [start_date]

            # CUSTOM: any weekday/date can be selected, up to 8 dates.
            # Past dates and Indian holidays remain unavailable.
            elif plan == "custom":
                booking_dates = list(custom_dates or [])

            # MONTHLY: four future, non-holiday occurrences of each selected
            # weekday, starting on or after the selected start date.
            elif plan == "monthly" and start_date and len(weekdays) == 2:
                per_weekday = PlanModel.MONTHLY_BOOKING_LIMIT // 2
                selected_weekdays = sorted(set(int(value) for value in weekdays))

                for weekday_value in selected_weekdays:
                    days_ahead = (weekday_value - start_date.weekday()) % 7
                    selected_date = start_date + timedelta(days=days_ahead)
                    count = 0

                    while count < per_weekday:
                        if (
                            selected_date >= today
                            and not holiday_name(selected_date)
                        ):
                            booking_dates.append(selected_date)
                            count += 1

                        selected_date += timedelta(days=7)

                booking_dates = sorted(booking_dates)

                if len(booking_dates) != PlanModel.MONTHLY_BOOKING_LIMIT:
                    form.add_error(
                        None,
                        "Could not generate all monthly dates for the selected weekdays."
                    )
            # .............
            if not form.errors:
                booking_dates = sorted(booking_dates)

                if not booking_dates:
                    form.add_error(None, "Please select at least one booking date.")

                elif len(booking_dates) != len(set(booking_dates)):
                    form.add_error(None, "Duplicate booking dates are not allowed.")

                elif any(selected_date < today for selected_date in booking_dates):
                    form.add_error(None, "Past dates par booking allowed nahi hai.")

                elif plan == "monthly" and len(booking_dates) != PlanModel.MONTHLY_BOOKING_LIMIT:
                    form.add_error(
                        None,
                        f"Monthly Plan ke liye exactly "
                        f"{PlanModel.MONTHLY_BOOKING_LIMIT} dates required hain."
                    )

                else:
                    # Basic and Custom cannot book on holidays.
                    holiday_bookings = [
                        (selected_date, holiday_name(selected_date))
                        for selected_date in booking_dates
                        if holiday_name(selected_date)
                    ]

                    if holiday_bookings:
                        labels = ", ".join(
                            f"{selected_date.isoformat()} ({name})"
                            for selected_date, name in holiday_bookings
                        )
                        form.add_error(
                            None,
                            f"Bookings cannot be made on holidays: {labels}."
                        )

            if not form.errors:
                price_per_slot = Decimal("300.00")
                total_price = price_per_slot * len(booking_dates)
                weekday_names = dict(PlanForm.WEEKDAY_CHOICES)

                selected_weekday_names = ", ".join(
                    weekday_names.get(str(value), str(value))
                    for value in weekdays
                ) if plan == "monthly" else ""

                try:
                    with transaction.atomic():
                        # Save individual date/time slots.
                        for selected_date in booking_dates:
                            slot = PlanModel(
                                user=current_user,
                                plan=plan,
                                time_Slot=time_slot,
                                date=selected_date,
                                price=price_per_slot,
                                username=current_user.username,
                            )
                            slot.full_clean()
                            slot.save()

                        # Save one summary record.
                        booking=Booking.objects.create(
                            user=current_user,
                            username=current_user.username,
                            plan=plan,
                            booking_status="pending",
                            weekdays=selected_weekday_names,
                            slot_time=time_slot,
                            start_date=booking_dates[0].isoformat(),
                            end_date=booking_dates[-1].isoformat(),
                            selected_dates=", ".join(
                                selected_date.isoformat()
                                for selected_date in booking_dates
                            ),
                            price=total_price,
                            payment_status="pending",
                        )
                        # payment record
                        Payment.objects.create(
                            booking=booking,
                            amount=total_price,
                            currency="INR",
                            payment_status="pending",
                        )

                except ValidationError as error:
                    if hasattr(error, "message_dict"):
                        for field, errors in error.message_dict.items():
                            if field in form.fields:
                                for message in errors:
                                    form.add_error(field, message)
                            else:
                                form.add_error(None, "; ".join(errors))
                    else:
                        form.add_error(None, error)

                else:
                    return redirect("payment", booking_id=booking.id)

    else:
        form = PlanForm(initial={"plan": "basic"})

    context = {
        "form": form,
        "profile": Profile.objects.filter(user_id=request.user).first(),
        "weekday_choices": PlanForm.WEEKDAY_CHOICES,
        "monthly_booking_limit": PlanModel.MONTHLY_BOOKING_LIMIT,
        "custom_booking_limit": PlanModel.CUSTOM_BOOKING_LIMIT,
    }
    return render(request, "booking.html", context)



@login_required(login_url="login")
def payment_view(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("payment"),
        id=booking_id,
        user=request.user,
    )

    payment = booking.payment
    payment_error = ""
    razorpay_key_id = settings.RAZORPAY_KEY_ID
    razorpay_key_secret = settings.RAZORPAY_KEY_SECRET

    if payment.payment_status == "success":
        messages.info(request, "This booking has already been paid.")
        return redirect("dashboard")

    if not razorpay_key_id or not razorpay_key_secret:
        payment_error = (
            "Online payment is not configured. Please contact the pool club."
        )
    elif booking.booking_status != "pending":
        payment_error = "This booking is no longer available for payment."
    elif not payment.razorpay_order_id:
        try:
            order = RazorpayClient(
                auth=(razorpay_key_id, razorpay_key_secret)
            ).order.create(data={
                "amount": int(payment.amount * 100),
                "currency": payment.currency,
                "receipt": f"payment-{payment.pk}",
                "notes": {
                    "booking_id": str(booking.pk),
                    "payment_id": str(payment.pk),
                },
            })
        except (
            BadRequestError,
            GatewayError,
            ServerError,
            RequestException,
        ):
            logger.exception(
                "Could not create Razorpay order for payment %s", payment.pk
            )
            payment_error = (
                "We could not start the payment right now. Please try again."
            )
        else:
            order_id = order.get("id")
            if (
                not order_id
                or order.get("amount") != int(payment.amount * 100)
                or order.get("currency") != payment.currency
            ):
                logger.error(
                    "Razorpay returned an invalid order for payment %s",
                    payment.pk,
                )
                payment_error = (
                    "We could not verify the payment order. Please try again."
                )
            else:
                payment.razorpay_order_id = order_id
                payment.save(update_fields=["razorpay_order_id", "updated_at"])

    context = {
        "booking": booking,
        "payment": payment,
        "profile": Profile.objects.filter(user_id=request.user).first(),
        "razorpay_key_id": razorpay_key_id,
        "razorpay_order_id": payment.razorpay_order_id,
        "amount_paise": int(payment.amount * 100),
        "payment_error": payment_error,
        "can_pay": (
            not payment_error
            and booking.booking_status == "pending"
            and payment.payment_status in {"pending", "failed"}
        ),
    }

    return render(request, "payment.html", context)


@login_required(login_url="login")
@require_POST
def verify_payment(request, booking_id):
    payment = get_object_or_404(
        Payment.objects.select_related("booking"),
        booking_id=booking_id,
        booking__user=request.user,
    )
    booking = payment.booking

    # Already paid check
    if payment.payment_status == "success":
        messages.info(request, "This booking has already been paid.")
        return redirect("dashboard")

    # Razorpay response
    payment_id = request.POST.get("razorpay_payment_id", "").strip()
    order_id = request.POST.get("razorpay_order_id", "").strip()
    signature = request.POST.get("razorpay_signature", "").strip()

    if (
        not payment.razorpay_order_id
        or order_id != payment.razorpay_order_id
        or not payment_id
        or not signature
    ):
        messages.error(
            request,
            "Payment verification failed. Please try again."
        )
        return redirect("payment", booking_id=booking.pk)

    # Razorpay credentials
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET

    if not key_id or not key_secret:
        messages.error(
            request,
            "Online payment is not configured. Please contact the pool club."
        )
        return redirect("payment", booking_id=booking.pk)

    # Verify Razorpay signature
    try:
        client = RazorpayClient(auth=(key_id, key_secret))

        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })

        # Verify actual payment status with Razorpay
        razorpay_payment = client.payment.fetch(payment_id)

        if (
            razorpay_payment.get("order_id") != order_id
            or razorpay_payment.get("status") != "captured"
            or razorpay_payment.get("amount") != int(payment.amount * 100)
            or razorpay_payment.get("currency") != payment.currency
        ):
            messages.error(
                request,
                "Payment is not captured or payment details do not match."
            )
            return redirect("payment", booking_id=booking.pk)

    except SignatureVerificationError:
        messages.error(
            request,
            "Payment verification failed. Please try again."
        )
        return redirect("payment", booking_id=booking.pk)

    except Exception:
        logger.exception(
            "Razorpay verification error for booking %s",
            booking.pk,
        )
        messages.error(
            request,
            "Unable to verify payment right now. Please contact support."
        )
        return redirect("payment", booking_id=booking.pk)

    # Update payment and booking status
    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().get(
            pk=payment.pk
        )
        locked_booking = Booking.objects.select_for_update().get(
            pk=booking.pk
        )

        if locked_payment.payment_status == "success":
            messages.info(
                request,
                "This booking has already been paid."
            )
            return redirect("dashboard")

        if (
            locked_payment.payment_status not in {"pending", "failed"}
            or locked_payment.razorpay_order_id != order_id
            or locked_booking.booking_status != "pending"
        ):
            messages.error(
                request,
                "This booking is no longer available for payment."
            )
            return redirect("payment", booking_id=booking.pk)

        locked_payment.payment_status = "success"
        locked_payment.razorpay_payment_id = payment_id
        locked_payment.razorpay_signature = signature
        locked_payment.save(update_fields=[
            "payment_status",
            "razorpay_payment_id",
            "razorpay_signature",
            "updated_at",
        ])

        locked_booking.booking_status = "success"
        locked_booking.payment_status = "success"
        locked_booking.save(update_fields=[
            "booking_status",
            "payment_status",
        ])

    # Send confirmation email after successful payment
    if request.user.email:
        try:
            send_mail(
                subject="Pool Booking Confirmed - Payment Successful",
                message=(
                    f"Hi {booking.username},\n\n"
                    "Your pool booking and payment have been confirmed!\n\n"
                    "========== BOOKING DETAILS ==========\n\n"
                    f"Booking ID: {booking.pk}\n"
                    f"Plan: {booking.get_plan_display()}\n"
                    f"Start Date: {booking.start_date}\n"
                    f"End Date: {booking.end_date or booking.start_date}\n"
                    f"Selected Dates: {booking.selected_dates}\n"
                    f"Time Slot: {booking.slot_time}\n"
                    f"Amount Paid: Rs. {payment.amount}\n"
                    f"Payment ID: {payment.razorpay_payment_id}\n"
                    f"Payment Status: {payment.payment_status.title()}\n\n"
                    "Your booking is confirmed for the dates and "
                    "time slot mentioned above.\n\n"
                    "Thank you for choosing our Pool Booking service!\n\n"
                    "Regards,\n"
                    "Pool Booking Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=False,
            )

        except Exception:
            logger.exception(
                "Confirmation email failed for booking %s",
                booking.pk,
            )
    else:
        logger.warning(
            "No email address available for booking %s",
            booking.pk,
        )

    messages.success(
        request,
        "Payment complete. Your booking is confirmed."
    )
    return redirect("dashboard")


@login_required(login_url="login")
def booking_detail(request):
    bookings = (
        Booking.objects
        .filter(user=request.user)
        .order_by("-id")
    )
    # print(bookings)
    context = {
        "bookings": bookings,
    }
    

    return render(request, "booking_detail.html", context)





# delete booking
@login_required(login_url="login")
def deleteBooking(request,id):
    book=Booking.objects.get(id=id)
    if book:
        book.delete()
        return redirect("booking_details")
    messages.error("user not found")

    return render(request,"CURD.html")
    

    


