from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(
    DEBUG=False,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class PortalAuthenticationTests(SimpleTestCase):
    def test_login_page_is_available(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Acceso al sistema interno')

    def test_operational_pages_redirect_anonymous_users_to_login(self):
        protected_urls = [
            reverse('dashboard'),
            reverse('cosecheros'),
            reverse('reporte_cosechero', args=[1, 1]),
            reverse('precios'),
            reverse('ventas'),
            reverse('tickets'),
            reverse('compras'),
            reverse('avances'),
        ]

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={url}",
                    fetch_redirect_response=False,
                )
