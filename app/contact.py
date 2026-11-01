"""Institutional staff email settings. Never sends mail or assumes SMTP access."""
import os
import re

OFFICIAL_DOMAIN = 'canariaseducacion.es'
_STAFF_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@canariaseducacion\.es\Z', re.ASCII)


def valid_staff_email(email: str) -> bool:
    """Validate literal mailbox domain without permitting subdomains or header injection."""
    return isinstance(email, str) and len(email) <= 150 and bool(_STAFF_EMAIL_PATTERN.fullmatch(email.strip()))


def configured_sender() -> str:
    """Optional authorised mailbox for RFC822 drafts; unset means no From header."""
    mailbox = os.environ.get('PORTACUSTODIA_CORREO_ORIGEN', '').strip()
    if mailbox and not valid_staff_email(mailbox):
        raise RuntimeError('PORTACUSTODIA_CORREO_ORIGEN debe ser una dirección @canariaseducacion.es válida.')
    return mailbox
