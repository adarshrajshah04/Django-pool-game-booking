from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from .forms import BookingUpdateForm
from .models import Booking, Payment, PlanModel, Profile


class DashboardHolidayViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="calendar-test",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.url = reverse("dashboard_holidays")

    def test_returns_festival_dates_for_requested_year(self):
        response = self.client.get(self.url, {"year": 2027})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["holidays"]["2027-03-22"], "Holi")

    def test_rejects_year_outside_supported_range(self):
        response = self.client.get(self.url, {"year": 2036})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_rejects_invalid_year(self):
        response = self.client.get(self.url, {"year": "not-a-year"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_requires_login(self):
        self.client.logout()

        response = self.client.get(self.url, {"year": 2027})

        self.assertEqual(response.status_code, 302)


class LogoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="logout-test",
        )
        self.client.force_login(self.user)
        self.url = reverse("logout")

    def test_post_logs_out_and_redirects_to_login(self):
        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False,
        )
        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            dashboard_response,
            reverse("login") + "?next=" + reverse("dashboard"),
        )

    def test_get_does_not_log_out(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)

    def test_logout_requires_authentication(self):
        self.client.logout()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class BookingPlanTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="booking-test")
        self.client.force_login(self.user)
        self.url = reverse("booking")
        self.base_booking = {
            "time_Slot": "09:00",
            "plan": "basic",
            "date": "2027-01-04",
            "weekdays": "",
            "custom_dates": "",
        }

    def test_booking_page_renders_plan_and_weekday_controls(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-plan="monthly"')
        self.assertContains(response, 'data-monthly-slot-limit="8"')
        self.assertContains(response, 'data-custom-slot-limit="8"')
        self.assertContains(response, 'data-weekday-choice="0"')
        self.assertContains(response, "Maximum 8 bookings")
        self.assertContains(response, 'querySelectorAll("[data-weekday-choice]")')
        self.assertContains(response, 'id="id_weekdays"')
        self.assertContains(response, 'id="id_custom_dates"')
        self.assertContains(response, 'class="booking-submit-section"')
        self.assertContains(response, "/dashboard/holidays/")
        self.assertContains(response, "function setAutomaticMonthlyStartDate(weekdays)")
        self.assertContains(response, "async function getMonthlyDates(weekdays)")
        self.assertNotContains(response, 'src=""')
        

    def test_dashboard_booking_link_opens_booking_page(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, 'data-dashboard-stat="total-slots"')
        self.assertContains(response, 'data-dashboard-stat="active-slots"')
        self.assertContains(response, 'data-dashboard-stat="holiday-shifted"')
        self.assertContains(response, 'data-dashboard-stat="cancelled-bookings"')
        self.assertContains(response, "<h2>0</h2>", count=4)

    def test_dashboard_booking_statistics_use_the_logged_in_users_records(self):
        booking_date = timezone.localdate() + timedelta(days=14)
        active_booking = Booking.objects.create(
            user=self.user,
            plan="basic",
            booking_status="success",
            username=self.user.username,
            slot_time="09:00",
            start_date=booking_date.isoformat(),
            selected_dates=booking_date.isoformat(),
            price=Decimal("600.00"),
            holiday_shifted_count=2,
        )
        for day_offset in range(2):
            PlanModel.objects.create(
                booking=active_booking,
                user=self.user,
                plan="basic",
                time_Slot="09:00",
                date=booking_date + timedelta(days=day_offset),
                price=Decimal("300.00"),
                username=self.user.username,
            )
        Booking.objects.create(
            user=self.user,
            plan="basic",
            booking_status="canceled",
            username=self.user.username,
            slot_time="10:00",
            start_date=booking_date.isoformat(),
            selected_dates=booking_date.isoformat(),
            price=Decimal("300.00"),
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_slots"], 2)
        self.assertEqual(response.context["active_slots"], 2)
        self.assertEqual(response.context["holiday_shifted"], 2)
        self.assertEqual(response.context["cancelled_bookings"], 1)

    @patch("myapp.views.country_holidays", return_value={})
    def test_basic_plan_can_be_booked_again(self, _country_holidays):
        first_date = "2027-01-04"
        second_date = "2027-01-05"

        for booking_date in (first_date, second_date):
            response = self.client.post(
                self.url,
                {**self.base_booking, "date": booking_date},
            )
            self.assertRedirects(
                response,
                reverse("payment", kwargs={"booking_id": Booking.objects.latest("id").id}),
                fetch_redirect_response=False,
            )

        self.assertEqual(PlanModel.objects.filter(user=self.user).count(), 2)

    @patch(
        "myapp.views.country_holidays",
        return_value={date(2027, 3, 22): "Holi"},
    )
    def test_monthly_plan_creates_eight_and_moves_holiday_to_same_weekday(
        self, _country_holidays
    ):
        response = self.client.post(
            self.url,
            {
                **self.base_booking,
                "plan": "monthly",
                "date": "2027-03-01",
                "weekdays": "0,1",
            },
        )

        self.assertRedirects(
            response,
            reverse("payment", kwargs={"booking_id": Booking.objects.latest("id").id}),
            fetch_redirect_response=False,
        )
        booking_dates = list(
            PlanModel.objects.filter(user=self.user)
            .order_by("date")
            .values_list("date", flat=True)
        )
        self.assertEqual(len(booking_dates), 8)
        self.assertNotIn(date(2027, 3, 22), booking_dates)
        self.assertIn(date(2027, 3, 29), booking_dates)
        self.assertTrue(all(booking_date.weekday() in (0, 1) for booking_date in booking_dates))
        self.assertEqual(len(booking_dates), PlanModel.MONTHLY_BOOKING_LIMIT)
        booking = Booking.objects.get(user=self.user)
        self.assertEqual(booking.holiday_shifted_count, 1)

    @patch("myapp.views.country_holidays", return_value={})
    def test_monthly_plan_completes_selected_weekdays_in_following_month(
        self, _country_holidays
    ):
        response = self.client.post(
            self.url,
            {
                **self.base_booking,
                "plan": "monthly",
                "date": "2027-03-29",
                "weekdays": "0,1",
            },
        )

        self.assertRedirects(
            response,
            reverse("payment", kwargs={"booking_id": Booking.objects.latest("id").id}),
            fetch_redirect_response=False,
        )
        booking_dates = list(
            PlanModel.objects.filter(user=self.user)
            .order_by("date")
            .values_list("date", flat=True)
        )
        self.assertEqual(len(booking_dates), PlanModel.MONTHLY_BOOKING_LIMIT)
        self.assertEqual(booking_dates[0], date(2027, 3, 29))
        self.assertEqual(booking_dates[-1], date(2027, 4, 20))
        self.assertTrue(all(booking_date.weekday() in (0, 1) for booking_date in booking_dates))
        booking = Booking.objects.get(user=self.user)
        self.assertEqual(booking.slots.count(), PlanModel.MONTHLY_BOOKING_LIMIT)
        self.assertEqual(booking.holiday_shifted_count, 0)

    @patch(
        "myapp.views.country_holidays",
        return_value={date(2027, 3, 22): "Holi"},
    )
    def test_basic_plan_rejects_holiday(self, _country_holidays):
        response = self.client.post(
            self.url,
            {**self.base_booking, "date": "2027-03-22"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bookings cannot be made on holidays")
        self.assertEqual(PlanModel.objects.count(), 0)

    @patch("myapp.views.country_holidays", return_value={})
    def test_booking_respects_slot_capacity(self, _country_holidays):
        PlanModel.objects.bulk_create([
            PlanModel(
                user=self.user,
                plan="basic",
                time_Slot="09:00",
                date=date(2027, 1, 4),
                price=Decimal("300.00"),
                username=self.user.username,
            )
            for _ in range(PlanModel.MAX_USERS_PER_SLOT)
        ])

        response = self.client.post(
            self.url,
            {**self.base_booking, "date": "2027-01-04"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This time slot is fully booked")
        self.assertEqual(PlanModel.objects.count(), PlanModel.MAX_USERS_PER_SLOT)

    @patch("myapp.views.country_holidays", return_value={})
    def test_custom_plan_rejects_more_than_eight_dates(self, _country_holidays):
        selected_dates = [
            (date(2028, 1, 1) + timedelta(days=day)).isoformat()
            for day in range(9)
        ]
        response = self.client.post(
            self.url,
            {
                **self.base_booking,
                "plan": "custom",
                "date": "",
                "custom_dates": ",".join(selected_dates),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose between 1 and 8 different dates")
        self.assertEqual(PlanModel.objects.count(), 0)

    @patch(
        "myapp.views.country_holidays",
        return_value={date(2027, 3, 22): "Holi"},
    )
    def test_custom_plan_rejects_holiday_dates(self, _country_holidays):
        response = self.client.post(
            self.url,
            {
                **self.base_booking,
                "plan": "custom",
                "date": "",
                "custom_dates": "2027-03-22",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bookings cannot be made on holidays")
        self.assertEqual(PlanModel.objects.count(), 0)

    @patch("myapp.views.country_holidays", return_value={})
    def test_monthly_plan_requires_two_weekdays(self, _country_holidays):
        response = self.client.post(
            self.url,
            {
                **self.base_booking,
                "plan": "monthly",
                "weekdays": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select exactly two different weekdays")
        self.assertEqual(PlanModel.objects.count(), 0)


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="payment-test")
        self.client.force_login(self.user)
        self.booking = Booking.objects.create(
            user=self.user,
            plan="basic",
            booking_status="pending",
            username=self.user.username,
            slot_time="09:00",
            start_date="2027-01-04",
            selected_dates="2027-01-04",
            price=Decimal("300.00"),
            payment_status="pending",
        )
        self.payment = Payment.objects.create(
            booking=self.booking,
            amount=Decimal("300.00"),
        )

    def test_payment_page_creates_order_and_renders_checkout(self):
        order = {
            "id": "order_test_123",
            "amount": 30000,
            "currency": "INR",
        }
        with (
            override_settings(
                RAZORPAY_KEY_ID="test_key",
                RAZORPAY_KEY_SECRET="test_secret",
            ),
            patch("myapp.views.RazorpayClient") as razorpay_client,
        ):
            razorpay_client.return_value.order.create.return_value = order
            response = self.client.get(
                reverse("payment", kwargs={"booking_id": self.booking.pk})
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete your payment")
        self.assertContains(response, "payment.css")
        self.assertContains(
            response,
            reverse("verify_payment", kwargs={"booking_id": self.booking.pk}),
        )
        self.assertEqual(self.payment.__class__.objects.get(pk=self.payment.pk).razorpay_order_id, order["id"])
        razorpay_client.return_value.order.create.assert_called_once()

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    @patch("myapp.views.RazorpayClient")
    def test_payment_page_repairs_legacy_booking_without_payment(self, razorpay_client):
        self.payment.delete()
        razorpay_client.return_value.order.create.return_value = {
            "id": "order_legacy_123",
            "amount": 30000,
            "currency": "INR",
        }

        response = self.client.get(
            reverse("payment", kwargs={"booking_id": self.booking.pk})
        )

        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.amount, self.booking.price)
        self.assertEqual(payment.razorpay_order_id, "order_legacy_123")

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_payment_page_reports_missing_gateway_configuration(self):
        response = self.client.get(
            reverse("payment", kwargs={"booking_id": self.booking.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Online payment is not configured")
        self.assertNotContains(response, 'id="pay-button"')

    def test_payment_page_does_not_expose_another_users_booking(self):
        other_user = get_user_model().objects.create_user(username="other-payment-user")
        other_booking = Booking.objects.create(
            user=other_user,
            plan="basic",
            username=other_user.username,
            slot_time="09:00",
            start_date="2027-01-04",
            price="300.00",
        )

        response = self.client.get(
            reverse("payment", kwargs={"booking_id": other_booking.pk})
        )

        self.assertEqual(response.status_code, 404)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    @patch("myapp.views.RazorpayClient")
    def test_verified_payment_confirms_booking(self, razorpay_client):
        self.payment.razorpay_order_id = "order_test_123"
        self.payment.save(update_fields=["razorpay_order_id", "updated_at"])
        razorpay_client.return_value.payment.fetch.return_value = {
            "order_id": "order_test_123",
            "status": "captured",
            "amount": 30000,
            "currency": "INR",
        }
        response = self.client.post(
            reverse("verify_payment", kwargs={"booking_id": self.booking.pk}),
            {
                "razorpay_payment_id": "pay_test_123",
                "razorpay_order_id": "order_test_123",
                "razorpay_signature": "valid_signature",
            },
        )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        razorpay_client.return_value.utility.verify_payment_signature.assert_called_once()
        self.payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.payment.payment_status, "success")
        self.assertEqual(self.payment.razorpay_payment_id, "pay_test_123")
        self.assertEqual(self.booking.payment_status, "success")
        self.assertEqual(self.booking.booking_status, "success")


class BookingManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="booking-management-test",
        )
        self.client.force_login(self.user)
        self.start_date = timezone.localdate() + timedelta(days=21)
        self.booking = Booking.objects.create(
            user=self.user,
            plan="basic",
            booking_status="success",
            username=self.user.username,
            slot_time="09:00",
            start_date=self.start_date.isoformat(),
            end_date=self.start_date.isoformat(),
            selected_dates=self.start_date.isoformat(),
            price=Decimal("300.00"),
            payment_status="success",
        )
        self.slot = PlanModel.objects.create(
            booking=self.booking,
            user=self.user,
            plan="basic",
            time_Slot="09:00",
            date=self.start_date,
            price=Decimal("300.00"),
            username=self.user.username,
        )
        self.action_url = reverse(
            "bookingAction",
            kwargs={"id": self.booking.pk},
        )

    def test_booking_update_renders_initial_date(self):
        response = self.client.get(self.action_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="start_date"')
        self.assertContains(response, self.start_date.isoformat())
        self.assertContains(response, "booking_action.css")

    def test_profile_image_remains_visible_on_booking_pages(self):
        Profile.objects.create(
            user_id=self.user,
            phone="1234567890",
            profile_image="profiles/test.jpg",
            age=25,
            gender="other",
        )

        for url in (reverse("booking_detail"), self.action_url):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'src="/media/profiles/test.jpg"')

    @patch("myapp.views.country_holidays", return_value={})
    def test_basic_booking_update_changes_booking_and_reserved_slot(
        self, _country_holidays
    ):
        new_date = self.start_date + timedelta(days=1)

        response = self.client.post(
            self.action_url,
            {
                "start_date": new_date.isoformat(),
                "slot_time": "10:00",
            },
        )

        self.assertRedirects(
            response,
            reverse("booking_detail"),
            fetch_redirect_response=False,
        )
        self.booking.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(self.booking.start_date, new_date.isoformat())
        self.assertEqual(self.booking.selected_dates, new_date.isoformat())
        self.assertEqual(self.booking.slot_time, "10:00")
        self.assertEqual(self.slot.date, new_date)
        self.assertEqual(self.slot.time_Slot, "10:00")

    @patch("myapp.views.country_holidays", return_value={})
    def test_monthly_update_changes_time_only_and_keeps_all_dates(
        self, _country_holidays
    ):
        monthly_dates = [
            self.start_date + timedelta(days=7 * index)
            for index in range(8)
        ]
        self.booking.plan = "monthly"
        self.booking.selected_dates = ", ".join(
            booking_date.isoformat() for booking_date in monthly_dates
        )
        self.booking.end_date = monthly_dates[-1].isoformat()
        self.booking.save()
        self.slot.plan = "monthly"
        self.slot.save()
        for booking_date in monthly_dates[1:]:
            PlanModel.objects.create(
                booking=self.booking,
                user=self.user,
                plan="monthly",
                time_Slot="09:00",
                date=booking_date,
                price=Decimal("300.00"),
                username=self.user.username,
            )

        get_response = self.client.get(self.action_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertNotContains(get_response, 'name="start_date"')
        self.assertContains(get_response, "You can only")

        response = self.client.post(
            self.action_url,
            {
                "start_date": (monthly_dates[0] + timedelta(days=14)).isoformat(),
                "slot_time": "11:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("booking_detail"),
            fetch_redirect_response=False,
        )
        self.booking.refresh_from_db()
        self.assertEqual(
            self.booking.selected_dates,
            ", ".join(value.isoformat() for value in monthly_dates),
        )
        self.assertEqual(self.booking.start_date, monthly_dates[0].isoformat())
        self.assertEqual(self.booking.end_date, monthly_dates[-1].isoformat())
        self.assertEqual(self.booking.slot_time, "11:00")
        self.assertFalse(BookingUpdateForm(instance=self.booking).fields.get("start_date"))
        self.assertEqual(
            list(
                PlanModel.objects.filter(booking=self.booking)
                .order_by("date")
                .values_list("date", flat=True)
            ),
            monthly_dates,
        )

    @patch("myapp.views.country_holidays", return_value={})
    def test_update_rejects_a_full_target_slot_without_changing_booking(
        self, _country_holidays
    ):
        new_date = self.start_date + timedelta(days=1)
        PlanModel.objects.bulk_create([
            PlanModel(
                user=self.user,
                plan="basic",
                time_Slot="10:00",
                date=new_date,
                price=Decimal("300.00"),
                username=self.user.username,
            )
            for _ in range(PlanModel.MAX_USERS_PER_SLOT)
        ])

        response = self.client.post(
            self.action_url,
            {
                "start_date": new_date.isoformat(),
                "slot_time": "10:00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "selected time is fully booked")
        self.booking.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(self.booking.start_date, self.start_date.isoformat())
        self.assertEqual(self.slot.date, self.start_date)

    def test_cancel_releases_slots_and_keeps_booking_and_payment_history(self):
        payment = Payment.objects.create(
            booking=self.booking,
            amount=self.booking.price,
            payment_status="success",
        )
        response = self.client.post(
            reverse("booking-canceling", kwargs={"id": self.booking.pk}),
        )

        self.assertRedirects(
            response,
            reverse("booking_detail"),
            fetch_redirect_response=False,
        )
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, "canceled")
        self.assertFalse(PlanModel.objects.filter(booking=self.booking).exists())
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_booking_actions_do_not_expose_another_users_booking(self):
        other_user = get_user_model().objects.create_user(
            username="other-booking-owner",
        )
        other_booking = Booking.objects.create(
            user=other_user,
            plan="basic",
            username=other_user.username,
            slot_time="09:00",
            start_date=self.start_date.isoformat(),
            price=Decimal("300.00"),
        )

        action_response = self.client.get(
            reverse("bookingAction", kwargs={"id": other_booking.pk}),
        )
        delete_response = self.client.post(
            reverse("booking-canceling", kwargs={"id": other_booking.pk}),
        )

        self.assertEqual(action_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)


class PaymentVerificationEdgeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="payment-edge-test",
        )
        self.client.force_login(self.user)
        self.booking = Booking.objects.create(
            user=self.user,
            plan="basic",
            booking_status="pending",
            username=self.user.username,
            slot_time="09:00",
            start_date="2027-01-04",
            selected_dates="2027-01-04",
            price=Decimal("300.00"),
            payment_status="pending",
        )
        self.payment = Payment.objects.create(
            booking=self.booking,
            amount=Decimal("300.00"),
        )

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    @patch("myapp.views.RazorpayClient")
    def test_invalid_signature_does_not_confirm_booking(self, razorpay_client):
        from razorpay.errors import SignatureVerificationError

        self.payment.razorpay_order_id = "order_test_123"
        self.payment.save(update_fields=["razorpay_order_id", "updated_at"])
        razorpay_client.return_value.utility.verify_payment_signature.side_effect = (
            SignatureVerificationError("invalid signature")
        )

        response = self.client.post(
            reverse("verify_payment", kwargs={"booking_id": self.booking.pk}),
            {
                "razorpay_payment_id": "pay_test_123",
                "razorpay_order_id": "order_test_123",
                "razorpay_signature": "invalid_signature",
            },
        )

        self.assertRedirects(
            response,
            reverse("payment", kwargs={"booking_id": self.booking.pk}),
            fetch_redirect_response=False,
        )
        self.payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.payment.payment_status, "pending")
        self.assertEqual(self.booking.booking_status, "pending")

    def test_payment_verification_rejects_another_users_booking(self):
        other_user = get_user_model().objects.create_user(username="other-verification-user")
        other_booking = Booking.objects.create(
            user=other_user,
            plan="basic",
            username=other_user.username,
            slot_time="09:00",
            start_date="2027-01-04",
            price="300.00",
        )

        response = self.client.post(
            reverse("verify_payment", kwargs={"booking_id": other_booking.pk}),
            {},
        )

        self.assertEqual(response.status_code, 404)
