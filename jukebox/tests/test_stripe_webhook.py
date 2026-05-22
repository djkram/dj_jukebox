"""
Tests per al Stripe webhook — el flux de pagament crític.

Cobreix:
- Signatura invàlida → 400
- checkout.session.completed → credits afegits + VotePackage creat + notificació
- Pagament duplicat (idempotència) → credits NO doblats
- Tipus d'event desconegut → ignorat (200)
- User/Party inexistents → resposta 200 sense crash
"""
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from jukebox.models import Party, VotePackage, Notification
from django.contrib.auth import get_user_model

User = get_user_model()

from django.urls import reverse


def _make_stripe_event(session_id, user_id, party_id, coins):
    """Construeix un MagicMock que imita un Stripe Event."""
    session = MagicMock()
    session.id = session_id
    session.metadata = {
        'user_id': str(user_id),
        'party_id': str(party_id),
        'votes_purchased': str(coins),
    }
    event = MagicMock()
    event.type = 'checkout.session.completed'
    event.data.object = session
    return event


class StripeWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='webhookuser', password='test', credits=0
        )
        self.party = Party.objects.create(
            name='Webhook Party', date=timezone.now()
        )

    def _post(self, body=b'payload', sig='sig_test'):
        return self.client.post(
            reverse('stripe_webhook'),
            data=body,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE=sig,
        )

    # --- Signatura ---

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_invalid_signature_returns_400(self, mock_construct):
        import stripe
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            'bad sig', 'sig_bad'
        )
        response = self._post()
        self.assertEqual(response.status_code, 400)

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_invalid_payload_returns_400(self, mock_construct):
        mock_construct.side_effect = ValueError('invalid payload')
        response = self._post()
        self.assertEqual(response.status_code, 400)

    # --- Happy path ---

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_coins_added_to_user(self, mock_construct):
        mock_construct.return_value = _make_stripe_event(
            'cs_test_001', self.user.id, self.party.id, 10
        )
        self._post()
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 10)

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_vote_package_created(self, mock_construct):
        mock_construct.return_value = _make_stripe_event(
            'cs_test_002', self.user.id, self.party.id, 25
        )
        self._post()
        self.assertTrue(
            VotePackage.objects.filter(
                payment_id='cs_test_002', user=self.user, party=self.party
            ).exists()
        )

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_notification_created_on_purchase(self, mock_construct):
        mock_construct.return_value = _make_stripe_event(
            'cs_test_003', self.user.id, self.party.id, 5
        )
        self._post()
        notif = Notification.objects.filter(
            user=self.user, type='coins_purchased'
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.amount, 5)

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_webhook_returns_200_on_success(self, mock_construct):
        mock_construct.return_value = _make_stripe_event(
            'cs_test_004', self.user.id, self.party.id, 10
        )
        response = self._post()
        self.assertEqual(response.status_code, 200)

    # --- Idempotència ---

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_duplicate_payment_does_not_add_coins_twice(self, mock_construct):
        VotePackage.objects.create(
            payment_id='cs_dup_001',
            user=self.user,
            party=self.party,
            votes_purchased=0,
        )
        mock_construct.return_value = _make_stripe_event(
            'cs_dup_001', self.user.id, self.party.id, 10
        )
        self._post()
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 0)

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_duplicate_payment_returns_200(self, mock_construct):
        VotePackage.objects.create(
            payment_id='cs_dup_002',
            user=self.user,
            party=self.party,
            votes_purchased=0,
        )
        mock_construct.return_value = _make_stripe_event(
            'cs_dup_002', self.user.id, self.party.id, 10
        )
        response = self._post()
        self.assertEqual(response.status_code, 200)

    # --- Tipus d'event desconegut ---

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_unknown_event_type_ignored(self, mock_construct):
        event = MagicMock()
        event.type = 'payment_intent.created'
        mock_construct.return_value = event
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 0)

    # --- Entitats inexistents ---

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_nonexistent_user_handled_gracefully(self, mock_construct):
        mock_construct.return_value = _make_stripe_event(
            'cs_test_nouser', 99999, self.party.id, 10
        )
        response = self._post()
        self.assertEqual(response.status_code, 200)

    @patch('jukebox.views.stripe.Webhook.construct_event')
    def test_nonexistent_party_handled_gracefully(self, mock_construct):
        mock_construct.return_value = _make_stripe_event(
            'cs_test_noparty', self.user.id, 99999, 10
        )
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 0)
