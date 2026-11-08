"""Email service — sends transactional emails via SMTP with language support.

v0.61b — template polish:
  - Full HTML5 doc with <head> for color-scheme meta, preheader, dark-mode
    media queries. Replaces the bare <div> wrapper used through v0.60.
  - Table-based layout for Outlook / mobile-client reliability.
  - @media (prefers-color-scheme: dark) overrides for Apple Mail, iOS Mail,
    Windows Mail, and Outlook.com where the user has dark mode on. Gmail's
    "differential dark mode" is not fully addressable from CSS — we rely on
    its default colour-inversion, which our palette tolerates.
  - Preheader text so inbox list shows "Confirm your spot" / similar instead
    of "Hi {name},".
  - Plain-text alternative attached alongside HTML for deliverability +
    accessibility + text-only clients.
  - Bulletproof CTA buttons ≥44px tall (iOS tap-target minimum).
  - The strings below are built-in defaults. Super admins can override
    registration confirmation and receipt copy per language from the form
    editor; the shared rendering/layout remains code-managed.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from html import escape as _html_escape

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Brand palette ───
# Keep in sync with frontend/src/index.css design tokens. Light values are the
# baseline (inline style); dark values are applied via media query classes.
_LIGHT_APP_BG = "#F7F5F2"
_LIGHT_CARD_BG = "#FFFFFF"
_LIGHT_TEXT_PRIMARY = "#0F1E2E"
_LIGHT_TEXT_MUTED = "#4B5A6B"
_LIGHT_TEXT_SUBTLE = "#8893A0"
_LIGHT_ACCENT = "#4682B4"  # Steel Blue
_LIGHT_CODE_BG = "#EAF2F9"

_DARK_APP_BG = "#0F1E2E"
_DARK_CARD_BG = "#1A2C40"
_DARK_TEXT_PRIMARY = "#F7F5F2"
_DARK_TEXT_MUTED = "#B4C0CC"
_DARK_ACCENT = "#FFD700"  # Gold
_DARK_CODE_BG = "#233A52"

_FONT_STACK = "'Nunito Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, Helvetica, sans-serif"

# ─── Translations for transactional emails ───
# v0.61b: English strings refined; other languages intentionally unchanged
# (the external translation pipeline will regenerate them in v0.70).
EMAIL_STRINGS = {
    'en': {
        'confirm_subject':          'Confirm your registration for {event}',
        'confirm_preheader':        'One quick click to save your spot.',
        'confirm_hi':               'Hi {name},',
        'confirm_body':             "Thanks for signing up for <strong>{event}</strong>. We just need you to confirm your registration so we can save your spot.",
        'confirm_button':           'Confirm registration',
        'confirm_fallback_pre':     "If the button above doesn't work, copy and paste this link into your browser:",
        'confirm_footer':           "If you didn't register for this event, you can safely ignore this email.",
        'receipt_subject':          "You're registered for {event}",
        'receipt_preheader':        'Your registration is confirmed. Here are the details.',
        'receipt_hi':               'Hi {name},',
        'receipt_body':             "You're all set for <strong>{event}</strong>. Your registration is confirmed.",
        'receipt_group_code_title': 'Your group code',
        'receipt_group_code_hint':  "Share this code with the people you'd like to be grouped with. When they register, they can enter this code to link up with you. You may also need it at check-in.",
        'receipt_closing':          "We'll be in touch with everything you need to know before the event.",
        'minor_form_subject':       'Consent form for {event}',
        'minor_form_preheader':     'Please complete and return the attached forms.',
        'minor_form_hi':            'Hi {name},',
        'minor_form_body':          "Because you will be under 18 on the event date, please have a parent or guardian complete the attached forms and upload the completed documents here: {upload_link}",
        'minor_form_closing':       'Please contact the event organisers if you need help.',
        'final_confirmation_subject':   'Your place at {event} is confirmed',
        'final_confirmation_preheader': 'Your registration is confirmed.',
        'final_confirmation_hi':        'Hi {name},',
        'final_confirmation_body':      "We're pleased to confirm that your registration for <strong>{event}</strong> is now confirmed.",
        'final_confirmation_closing':   'We look forward to seeing you at the event.',
        'reminder_subject':         'Payment reminder for {event}',
        'reminder_preheader':       'A quick reminder about your event fee.',
        'reminder_hi':              'Hi {name},',
        'reminder_body':            "Our records show that your registration for <strong>{event}</strong> is still awaiting payment. It has been {days} days since you registered. Please arrange payment as soon as possible.",
        'reminder_closing':         'If you have already paid, please disregard this message.',
        'cancellation_subject':     'Your registration for {event} has been cancelled',
        'cancellation_preheader':   'An update about your event registration.',
        'cancellation_hi':          'Hi {name},',
        'cancellation_body':        "Your registration for <strong>{event}</strong> has been cancelled by the organisers. Please contact the organisers if you think this was a mistake.",
        'cancellation_closing':     'We are sorry you will not be joining us.',
        'powered_by':               'Powered by Moimio',
    },
    # ── untouched — regenerated in v0.70 ───────────────────────────────
    'de': {
        'confirm_subject': 'Bitte bestätige deine Anmeldung — {event}',
        'confirm_preheader': 'Bitte bestätige deine Anmeldung.',
        'confirm_hi': 'Hallo {name},',
        'confirm_body': 'Vielen Dank für deine Anmeldung für <strong>{event}</strong>. Bitte bestätige deine Anmeldung über den folgenden Button:',
        'confirm_button': 'Anmeldung bestätigen',
        'confirm_fallback_pre': 'Falls der Button nicht funktioniert, kopiere diesen Link in deinen Browser:',
        'confirm_footer': 'Wenn du dich nicht für dieses Event angemeldet hast, kannst du diese E-Mail ignorieren.',
        'receipt_subject': 'Anmeldung bestätigt — {event}',
        'receipt_preheader': 'Deine Anmeldung ist bestätigt.',
        'receipt_hi': 'Hallo {name},',
        'receipt_body': 'Deine Anmeldung für <strong>{event}</strong> wurde bestätigt. ✓',
        'receipt_group_code_title': 'Dein Gruppencode',
        'receipt_group_code_hint': 'Teile diesen Code mit den Mitgliedern deiner Gruppe, wenn sie sich anmelden. Sie können diesen Code den Organisatoren mitteilen, um für Zimmer- und Gruppenzuweisungen verknüpft zu werden.',
        'receipt_closing': 'Das Organisationsteam wird sich in Kürze mit weiteren Informationen melden.',
        'minor_form_subject': 'Einverständniserklärung für {event}',
        'minor_form_preheader': 'Bitte füllt die beigefügten Formulare aus und ladet sie hoch.',
        'minor_form_hi': 'Hallo {name},',
        'minor_form_body': 'Da du am Veranstaltungstag unter 18 Jahre alt sein wirst, bitten wir deine Eltern oder Erziehungsberechtigten, die beigefügten Formulare auszufüllen und hier hochzuladen: {upload_link}',
        'minor_form_closing': 'Bei Fragen wende dich bitte an das Organisationsteam.',
        'final_confirmation_subject': 'Dein Platz bei {event} ist bestätigt',
        'final_confirmation_preheader': 'Deine Anmeldung ist bestätigt.',
        'final_confirmation_hi': 'Hallo {name},',
        'final_confirmation_body': 'Wir freuen uns, dir mitzuteilen, dass deine Anmeldung für <strong>{event}</strong> nun bestätigt ist.',
        'final_confirmation_closing': 'Wir freuen uns darauf, dich bei der Veranstaltung zu sehen.',
        'reminder_subject': 'Zahlungserinnerung für {event}',
        'reminder_preheader': 'Eine kurze Erinnerung an die Veranstaltungsgebühr.',
        'reminder_hi': 'Hallo {name},',
        'reminder_body': 'Laut unseren Unterlagen steht die Zahlung für deine Anmeldung zu <strong>{event}</strong> noch aus. Seit deiner Anmeldung sind {days} Tage vergangen. Bitte veranlasse die Zahlung so bald wie möglich.',
        'reminder_closing': 'Falls du bereits bezahlt hast, ignoriere diese Nachricht bitte.',
        'cancellation_subject': 'Deine Anmeldung für {event} wurde storniert',
        'cancellation_preheader': 'Eine Neuigkeit zu deiner Veranstaltungsanmeldung.',
        'cancellation_hi': 'Hallo {name},',
        'cancellation_body': 'Die Organisatoren haben deine Anmeldung für <strong>{event}</strong> storniert. Bitte kontaktiere sie, falls dies ein Irrtum ist.',
        'cancellation_closing': 'Schade, dass du nicht dabei sein wirst.',
        'powered_by': 'Powered by Moimio',
    },
    'ko': {
        'confirm_subject': '등록 확인 요청 — {event}',
        'confirm_preheader': '등록을 확인해 주세요.',
        'confirm_hi': '{name}님, 안녕하세요.',
        'confirm_body': '<strong>{event}</strong> 행사에 등록해 주셔서 감사합니다. 아래 버튼을 클릭하여 등록을 확인해 주세요:',
        'confirm_button': '등록 확인',
        'confirm_fallback_pre': '버튼이 작동하지 않는 경우 아래 링크를 브라우저에 복사해 주세요:',
        'confirm_footer': '이 행사에 등록하지 않으셨다면 이 이메일을 무시하셔도 됩니다.',
        'receipt_subject': '등록 완료 — {event}',
        'receipt_preheader': '등록이 완료되었습니다.',
        'receipt_hi': '{name}님, 안녕하세요.',
        'receipt_body': '<strong>{event}</strong> 행사 등록이 완료되었습니다. ✓',
        'receipt_group_code_title': '그룹 코드',
        'receipt_group_code_hint': '그룹원이 등록할 때 이 코드를 공유해 주세요. 주최자에게 이 코드를 알려주시면 방 및 그룹 배정 시 함께 묶입니다.',
        'receipt_closing': '주최팀에서 추가 정보를 곧 보내드릴 것입니다.',
        'minor_form_subject': '{event} 보호자 동의서',
        'minor_form_preheader': '첨부된 양식을 작성하여 제출해 주세요.',
        'minor_form_hi': '{name}님, 안녕하세요.',
        'minor_form_body': '행사 당일 만 18세 미만이므로 보호자께서 첨부된 양식을 모두 작성한 후 아래 링크에서 제출해 주세요: {upload_link}',
        'minor_form_closing': '도움이 필요하시면 행사 주최자에게 문의해 주세요.',
        'final_confirmation_subject': '{event} 참가가 확정되었습니다',
        'final_confirmation_preheader': '등록이 확정되었습니다.',
        'final_confirmation_hi': '{name}님, 안녕하세요.',
        'final_confirmation_body': '<strong>{event}</strong> 행사 참가가 확정되었음을 알려드립니다.',
        'final_confirmation_closing': '행사에서 뵙기를 기대합니다.',
        'reminder_subject': '{event} 참가비 납부 안내',
        'reminder_preheader': '행사 참가비 납부에 관한 안내입니다.',
        'reminder_hi': '{name}님, 안녕하세요.',
        'reminder_body': '<strong>{event}</strong> 행사 등록 후 {days}일이 지났으며 아직 참가비 납부가 확인되지 않았습니다. 가능한 한 빨리 납부해 주세요.',
        'reminder_closing': '이미 납부하셨다면 이 안내를 무시해 주세요.',
        'cancellation_subject': '{event} 등록이 취소되었습니다',
        'cancellation_preheader': '행사 등록에 관한 안내입니다.',
        'cancellation_hi': '{name}님, 안녕하세요.',
        'cancellation_body': '주최자가 <strong>{event}</strong> 행사 등록을 취소했습니다. 잘못된 안내라고 생각하시면 주최자에게 문의해 주세요.',
        'cancellation_closing': '함께하지 못하게 되어 아쉽습니다.',
        'powered_by': 'Moimio 제공',
    },
    'es': {
        'confirm_subject': 'Confirma tu inscripción — {event}',
        'confirm_preheader': 'Confirma tu inscripción.',
        'confirm_hi': 'Hola {name},',
        'confirm_body': 'Gracias por inscribirte en <strong>{event}</strong>. Por favor confirma tu inscripción haciendo clic en el botón de abajo:',
        'confirm_button': 'Confirmar inscripción',
        'confirm_fallback_pre': 'Si el botón no funciona, copia y pega este enlace en tu navegador:',
        'confirm_footer': 'Si no te inscribiste en este evento, puedes ignorar este correo.',
        'receipt_subject': 'Inscripción confirmada — {event}',
        'receipt_preheader': 'Tu inscripción está confirmada.',
        'receipt_hi': 'Hola {name},',
        'receipt_body': 'Tu inscripción en <strong>{event}</strong> ha sido confirmada. ✓',
        'receipt_group_code_title': 'Tu código de grupo',
        'receipt_group_code_hint': 'Comparte este código con los miembros de tu grupo cuando se inscriban para que se les agrupe contigo.',
        'receipt_closing': 'El equipo organizador te enviará más información pronto.',
        'minor_form_subject': 'Formulario de consentimiento para {event}',
        'minor_form_preheader': 'Completa y envía los formularios adjuntos.',
        'minor_form_hi': 'Hola {name},',
        'minor_form_body': 'Como tendrás menos de 18 años en la fecha del evento, pide a tu padre, madre o tutor que complete los formularios adjuntos y los suba aquí: {upload_link}',
        'minor_form_closing': 'Si necesitas ayuda, ponte en contacto con la organización.',
        'final_confirmation_subject': 'Tu plaza en {event} está confirmada',
        'final_confirmation_preheader': 'Tu inscripción está confirmada.',
        'final_confirmation_hi': 'Hola {name},',
        'final_confirmation_body': 'Nos complace confirmarte que tu inscripción a <strong>{event}</strong> ya está confirmada.',
        'final_confirmation_closing': 'Esperamos verte en el evento.',
        'reminder_subject': 'Recordatorio de pago para {event}',
        'reminder_preheader': 'Un recordatorio sobre la cuota del evento.',
        'reminder_hi': 'Hola {name},',
        'reminder_body': 'Según nuestros registros, aún está pendiente el pago de tu inscripción a <strong>{event}</strong>. Han pasado {days} días desde que te inscribiste. Por favor, realiza el pago lo antes posible.',
        'reminder_closing': 'Si ya pagaste, puedes ignorar este mensaje.',
        'cancellation_subject': 'Tu inscripción a {event} ha sido cancelada',
        'cancellation_preheader': 'Una actualización sobre tu inscripción al evento.',
        'cancellation_hi': 'Hola {name},',
        'cancellation_body': 'Los organizadores han cancelado tu inscripción a <strong>{event}</strong>. Si crees que esto es un error, ponte en contacto con ellos.',
        'cancellation_closing': 'Lamentamos que no puedas acompañarnos.',
        'powered_by': 'Desarrollado por Moimio',
    },
    'pt-BR': {
        'confirm_subject': 'Confirme sua inscrição — {event}',
        'confirm_preheader': 'Confirme sua inscrição.',
        'confirm_hi': 'Olá {name},',
        'confirm_body': 'Obrigado por se inscrever em <strong>{event}</strong>. Por favor, confirme sua inscrição clicando no botão abaixo:',
        'confirm_button': 'Confirmar inscrição',
        'confirm_fallback_pre': 'Se o botão não funcionar, copie e cole este link no seu navegador:',
        'confirm_footer': 'Se você não se inscreveu neste evento, pode ignorar este e-mail.',
        'receipt_subject': 'Inscrição confirmada — {event}',
        'receipt_preheader': 'Sua inscrição está confirmada.',
        'receipt_hi': 'Olá {name},',
        'receipt_body': 'Sua inscrição em <strong>{event}</strong> foi confirmada. ✓',
        'receipt_group_code_title': 'Seu código de grupo',
        'receipt_group_code_hint': 'Compartilhe este código com os membros do seu grupo ao se inscreverem para que sejam agrupados com você.',
        'receipt_closing': 'A equipe organizadora enviará mais informações em breve.',
        'minor_form_subject': 'Formulário de consentimento para {event}',
        'minor_form_preheader': 'Preencha e envie os formulários anexados.',
        'minor_form_hi': 'Olá {name},',
        'minor_form_body': 'Como você terá menos de 18 anos na data do evento, peça a um responsável que preencha os formulários anexados e envie-os aqui: {upload_link}',
        'minor_form_closing': 'Se precisar de ajuda, entre em contato com a organização.',
        'final_confirmation_subject': 'Sua vaga em {event} está confirmada',
        'final_confirmation_preheader': 'Sua inscrição está confirmada.',
        'final_confirmation_hi': 'Olá {name},',
        'final_confirmation_body': 'Temos o prazer de confirmar que sua inscrição em <strong>{event}</strong> foi confirmada.',
        'final_confirmation_closing': 'Esperamos encontrar você no evento.',
        'reminder_subject': 'Lembrete de pagamento para {event}',
        'reminder_preheader': 'Um lembrete sobre a taxa do evento.',
        'reminder_hi': 'Olá {name},',
        'reminder_body': 'Nossos registros indicam que o pagamento da sua inscrição em <strong>{event}</strong> ainda está pendente. Já se passaram {days} dias desde a sua inscrição. Por favor, providencie o pagamento assim que possível.',
        'reminder_closing': 'Se você já pagou, desconsidere esta mensagem.',
        'cancellation_subject': 'Sua inscrição em {event} foi cancelada',
        'cancellation_preheader': 'Uma atualização sobre sua inscrição no evento.',
        'cancellation_hi': 'Olá {name},',
        'cancellation_body': 'A equipe organizadora cancelou sua inscrição em <strong>{event}</strong>. Se você acredita que isso foi um engano, entre em contato com a organização.',
        'cancellation_closing': 'Sentimos muito que você não poderá participar.',
        'powered_by': 'Desenvolvido por Moimio',
    },
    'fr': {
        'confirm_subject': 'Confirmez votre inscription — {event}',
        'confirm_preheader': 'Confirmez votre inscription.',
        'confirm_hi': 'Bonjour {name},',
        'confirm_body': "Merci de vous être inscrit(e) à <strong>{event}</strong>. Veuillez confirmer votre inscription en cliquant sur le bouton ci-dessous :",
        'confirm_button': "Confirmer l'inscription",
        'confirm_fallback_pre': 'Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :',
        'confirm_footer': "Si vous ne vous êtes pas inscrit(e) à cet événement, vous pouvez ignorer cet e-mail.",
        'receipt_subject': 'Inscription confirmée — {event}',
        'receipt_preheader': 'Votre inscription est confirmée.',
        'receipt_hi': 'Bonjour {name},',
        'receipt_body': 'Votre inscription à <strong>{event}</strong> a été confirmée. ✓',
        'receipt_group_code_title': 'Votre code de groupe',
        'receipt_group_code_hint': 'Partagez ce code avec les membres de votre groupe lors de leur inscription pour être regroupés ensemble.',
        'receipt_closing': "L'équipe organisatrice vous enverra de plus amples informations bientôt.",
        'minor_form_subject': 'Formulaire de consentement pour {event}',
        'minor_form_preheader': 'Veuillez remplir et renvoyer les formulaires joints.',
        'minor_form_hi': 'Bonjour {name},',
        'minor_form_body': "Comme vous aurez moins de 18 ans à la date de l'événement, demandez à votre parent ou tuteur de remplir les formulaires joints et de les déposer ici : {upload_link}",
        'minor_form_closing': "Si vous avez besoin d'aide, veuillez contacter l'équipe organisatrice.",
        'final_confirmation_subject': 'Votre place à {event} est confirmée',
        'final_confirmation_preheader': 'Votre inscription est confirmée.',
        'final_confirmation_hi': 'Bonjour {name},',
        'final_confirmation_body': 'Nous avons le plaisir de vous confirmer que votre inscription à <strong>{event}</strong> est maintenant confirmée.',
        'final_confirmation_closing': 'Nous avons hâte de vous retrouver lors de l’événement.',
        'reminder_subject': 'Rappel de paiement pour {event}',
        'reminder_preheader': 'Un rappel au sujet des frais de participation.',
        'reminder_hi': 'Bonjour {name},',
        'reminder_body': "D'après nos informations, le paiement de votre inscription à <strong>{event}</strong> est toujours en attente. {days} jours se sont écoulés depuis votre inscription. Merci de procéder au paiement dès que possible.",
        'reminder_closing': 'Si vous avez déjà payé, veuillez ignorer ce message.',
        'cancellation_subject': 'Votre inscription à {event} a été annulée',
        'cancellation_preheader': 'Une information concernant votre inscription à l’événement.',
        'cancellation_hi': 'Bonjour {name},',
        'cancellation_body': "L'équipe organisatrice a annulé votre inscription à <strong>{event}</strong>. Si vous pensez qu'il s'agit d'une erreur, veuillez la contacter.",
        'cancellation_closing': 'Nous sommes désolés que vous ne puissiez pas être des nôtres.',
        'powered_by': 'Propulsé par Moimio',
    },
}


def _s(lang: str, key: str) -> str:
    """Get a translated string, falling back to English."""
    return EMAIL_STRINGS.get(lang, EMAIL_STRINGS['en']).get(key, EMAIL_STRINGS['en'][key])


def _template_string(key: str, lang: str, email_strings: dict[str, str] | None) -> str:
    return (email_strings or {}).get(key, _s(lang, key))


# ─── HTML building blocks ─────────────────────────────────────────────────

def _shell(*, title: str, preheader: str, body_html: str, lang: str = 'en') -> str:
    """Wrap content in a full HTML5 document with dark-mode support."""
    # Hidden preheader — harvested as inbox preview but invisible on open.
    # Trailing padding chars prevent leakage from body content.
    hidden_preheader = (
        f'<div style="display:none; font-size:1px; color:{_LIGHT_APP_BG}; '
        f'line-height:1px; max-height:0px; max-width:0px; opacity:0; overflow:hidden; '
        f'mso-hide:all;">{_html_escape(preheader)}'
        f'&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;&#8199;&#65279;</div>'
    )

    return f"""<!doctype html>
<html lang="{_html_escape(lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{_html_escape(title)}</title>
<style>
  body {{ margin: 0 !important; padding: 0 !important; width: 100% !important; -webkit-font-smoothing: antialiased; }}
  table {{ border-collapse: collapse; }}
  img {{ border: 0; display: block; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }}
  a {{ text-decoration: none; }}

  @media only screen and (max-width: 480px) {{
    .m-px-16 {{ padding-left: 16px !important; padding-right: 16px !important; }}
    .m-py-24 {{ padding-top: 24px !important; padding-bottom: 24px !important; }}
    .m-button {{ display: block !important; width: 100% !important; box-sizing: border-box !important; }}
  }}

  @media (prefers-color-scheme: dark) {{
    .app-bg      {{ background-color: {_DARK_APP_BG} !important; }}
    .card-bg     {{ background-color: {_DARK_CARD_BG} !important; }}
    .text-primary {{ color: {_DARK_TEXT_PRIMARY} !important; }}
    .text-muted  {{ color: {_DARK_TEXT_MUTED} !important; }}
    .text-subtle {{ color: {_DARK_TEXT_MUTED} !important; }}
    .cta-btn     {{ background-color: {_DARK_ACCENT} !important; color: {_DARK_APP_BG} !important; }}
    .cta-btn a   {{ color: {_DARK_APP_BG} !important; }}
    .code-bg     {{ background-color: {_DARK_CODE_BG} !important; }}
    .code-value  {{ color: {_DARK_ACCENT} !important; }}
    .logo-accent {{ color: {_DARK_ACCENT} !important; }}
    .hairline    {{ border-color: rgba(255,255,255,0.08) !important; }}
  }}

  [data-ogsc] .app-bg      {{ background-color: {_DARK_APP_BG} !important; }}
  [data-ogsc] .card-bg     {{ background-color: {_DARK_CARD_BG} !important; }}
  [data-ogsc] .text-primary {{ color: {_DARK_TEXT_PRIMARY} !important; }}
  [data-ogsc] .text-muted  {{ color: {_DARK_TEXT_MUTED} !important; }}
  [data-ogsc] .text-subtle {{ color: {_DARK_TEXT_MUTED} !important; }}
  [data-ogsc] .cta-btn     {{ background-color: {_DARK_ACCENT} !important; color: {_DARK_APP_BG} !important; }}
  [data-ogsc] .cta-btn a   {{ color: {_DARK_APP_BG} !important; }}
  [data-ogsc] .code-bg     {{ background-color: {_DARK_CODE_BG} !important; }}
  [data-ogsc] .code-value  {{ color: {_DARK_ACCENT} !important; }}
  [data-ogsc] .logo-accent {{ color: {_DARK_ACCENT} !important; }}
</style>
</head>
<body class="app-bg" style="background-color: {_LIGHT_APP_BG}; margin: 0; padding: 0;">
{hidden_preheader}
<table role="presentation" class="app-bg" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: {_LIGHT_APP_BG};">
  <tr>
    <td align="center" style="padding: 32px 16px;">
      <table role="presentation" class="card-bg" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width: 540px; background-color: {_LIGHT_CARD_BG}; border-radius: 12px;">
        <tr>
          <td class="m-px-16 m-py-24" style="padding: 32px; font-family: {_FONT_STACK}; font-size: 15px; line-height: 1.55; color: {_LIGHT_TEXT_PRIMARY};">
            {body_html}
          </td>
        </tr>
      </table>
      <p class="text-subtle" style="margin: 16px 0 0 0; font-family: {_FONT_STACK}; font-size: 11px; color: {_LIGHT_TEXT_SUBTLE};">
        {_html_escape(_s(lang, 'powered_by'))}
      </p>
    </td>
  </tr>
</table>
</body>
</html>"""


def _logo() -> str:
    """Brand wordmark — two-tone split."""
    return (
        f'<div style="margin: 0 0 20px 0; font-family: {_FONT_STACK}; '
        f'font-weight: 800; font-size: 22px; letter-spacing: 0.01em;">'
        f'<span class="text-primary" style="color: {_LIGHT_TEXT_PRIMARY};">MOIM</span>'
        f'<span class="logo-accent" style="color: {_LIGHT_ACCENT}; font-size: 0.7em; vertical-align: baseline;">io</span>'
        f'</div>'
    )


def _button(url: str, label: str) -> str:
    """Bulletproof CTA button — ≥44px tall, full-width on mobile."""
    safe_url = _html_escape(url, quote=True)
    safe_label = _html_escape(label)
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin: 24px 0;">
  <tr>
    <td align="center" bgcolor="{_LIGHT_ACCENT}" class="cta-btn" style="background-color: {_LIGHT_ACCENT}; border-radius: 8px;">
      <a href="{safe_url}" class="m-button" style="display: inline-block; padding: 14px 28px; font-family: {_FONT_STACK}; font-size: 15px; font-weight: 700; color: #FFFFFF; text-decoration: none; border-radius: 8px; mso-padding-alt: 0; line-height: 1.2;">
        <!--[if mso]>&nbsp;&nbsp;&nbsp;<![endif]-->{safe_label}<!--[if mso]>&nbsp;&nbsp;&nbsp;<![endif]-->
      </a>
    </td>
  </tr>
</table>"""


def _p(text: str, *, muted: bool = False, size: str = "15px", margin_top: str = "0") -> str:
    """Paragraph helper. `text` may contain trusted inline HTML (e.g. <strong>)."""
    color = _LIGHT_TEXT_MUTED if muted else _LIGHT_TEXT_PRIMARY
    klass = "text-muted" if muted else "text-primary"
    return (
        f'<p class="{klass}" style="margin: {margin_top} 0 12px 0; '
        f'font-family: {_FONT_STACK}; font-size: {size}; line-height: 1.55; '
        f'color: {color};">{text}</p>'
    )


def _hairline() -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'class="hairline" style="border-top: 1px solid rgba(15,30,46,0.08); margin: 20px 0;">'
        f'<tr><td style="height:0; line-height:0;">&nbsp;</td></tr></table>'
    )


def _html_to_text(html_like: str) -> str:
    """Minimal HTML→text for the plain-text alternative."""
    s = html_like
    for tag in ('<strong>', '</strong>', '<em>', '</em>', '<b>', '</b>', '<i>', '</i>'):
        s = s.replace(tag, '')
    return s


# ─── SMTP transport ───────────────────────────────────────────────────────

def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """Send an email. Returns True on success, False otherwise.

    v0.61b: accepts optional plain-text alternative. When provided, it's
    attached first so it becomes the fallback for text-only clients; the
    HTML part is attached second so it's preferred by HTML-capable clients
    (RFC 2046 §5.1.4 — last alternative wins).
    """
    settings = get_settings()

    if not settings.smtp_enabled:
        logger.warning("email_skipped", reason="SMTP not configured", to=to_email)
        return False

    try:
        msg = MIMEMultipart("mixed" if attachments else "alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = to_email
        if attachments:
            alternatives = MIMEMultipart("alternative")
            if text_body:
                alternatives.attach(MIMEText(text_body, "plain", "utf-8"))
            alternatives.attach(MIMEText(html_body, "html", "utf-8"))
            msg.attach(alternatives)
            for filename, content, media_type in attachments:
                maintype, subtype = media_type.split("/", 1)
                attachment = MIMEApplication(content, _subtype=subtype)
                attachment.add_header(
                    "Content-Disposition", "attachment", filename=filename
                )
                msg.attach(attachment)
        else:
            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        if settings.smtp_ssl:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port)
        elif settings.smtp_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)

        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, to_email, msg.as_string())
        server.quit()

        logger.info("email_sent", to=to_email, subject=subject)
        return True

    except Exception as e:
        logger.error("email_failed", to=to_email, error=str(e))
        return False


# ─── Transactional emails ─────────────────────────────────────────────────

def send_confirmation_email(
    to_email: str, first_name: str, event_name: str, confirmation_url: str, lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    """Ask a participant to confirm their pending registration."""
    L = lang if lang in EMAIL_STRINGS else 'en'
    subject = _template_string('confirm_subject', L, email_strings).format(event=event_name)

    safe_url = _html_escape(confirmation_url, quote=True)

    body_html = (
        _logo()
        + _p(_safe_template_html(_template_string('confirm_hi', L, email_strings).format(name=first_name)))
        + _p(_safe_template_html(_template_string('confirm_body', L, email_strings).format(event=event_name)))
        + _button(confirmation_url, _template_string('confirm_button', L, email_strings))
        + _p(_safe_template_html(_template_string('confirm_fallback_pre', L, email_strings)), muted=True, size="13px", margin_top="8px")
        + f'<p class="text-muted" style="margin: 0 0 20px 0; font-family: {_FONT_STACK}; '
          f'font-size: 12px; line-height: 1.5; word-break: break-all; color: {_LIGHT_TEXT_MUTED};">'
          f'<a href="{safe_url}" class="logo-accent" '
          f'style="color: {_LIGHT_ACCENT}; text-decoration: underline;">'
          f'{_html_escape(confirmation_url)}</a></p>'
        + _hairline()
        + _p(_safe_template_html(_template_string('confirm_footer', L, email_strings)), muted=True, size="12px")
    )

    html = _shell(
        title=subject,
        preheader=_template_string('confirm_preheader', L, email_strings),
        body_html=body_html,
        lang=L,
    )

    text = (
        f"{_html_to_text(_template_string('confirm_hi', L, email_strings).format(name=first_name))}\n\n"
        f"{_html_to_text(_template_string('confirm_body', L, email_strings).format(event=event_name))}\n\n"
        f"{_template_string('confirm_button', L, email_strings)}:\n{confirmation_url}\n\n"
        f"{_template_string('confirm_footer', L, email_strings)}\n\n"
        f"— {_s(L, 'powered_by')}\n"
    )

    return send_email(to_email, subject, html, text)


def send_registration_confirmed(
    to_email: str, first_name: str, event_name: str, group_code: str | None = None, lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    """Send a post-confirmation receipt. Includes the group code when present."""
    L = lang if lang in EMAIL_STRINGS else 'en'
    subject = _template_string('receipt_subject', L, email_strings).format(event=event_name)

    group_code_section = ""
    if group_code:
        safe_code = _html_escape(group_code)
        group_code_section = f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       class="code-bg" style="background-color: {_LIGHT_CODE_BG}; border-radius: 10px; margin: 4px 0 16px 0;">
  <tr>
    <td style="padding: 16px 20px;">
      <p class="text-subtle" style="margin: 0 0 6px 0; font-family: {_FONT_STACK}; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: {_LIGHT_TEXT_SUBTLE};">
        {_html_escape(_template_string('receipt_group_code_title', L, email_strings))}
      </p>
      <p class="code-value" style="margin: 0 0 10px 0; font-family: 'Courier New', Consolas, monospace; font-size: 22px; font-weight: 700; letter-spacing: 3px; color: {_LIGHT_ACCENT};">
        {safe_code}
      </p>
      <p class="text-muted" style="margin: 0; font-family: {_FONT_STACK}; font-size: 12px; line-height: 1.5; color: {_LIGHT_TEXT_MUTED};">
        {_html_escape(_template_string('receipt_group_code_hint', L, email_strings))}
      </p>
    </td>
  </tr>
</table>"""

    body_html = (
        _logo()
        + _p(_safe_template_html(_template_string('receipt_hi', L, email_strings).format(name=first_name)))
        + _p(_safe_template_html(_template_string('receipt_body', L, email_strings).format(event=event_name)))
        + group_code_section
        + _p(_safe_template_html(_template_string('receipt_closing', L, email_strings)), muted=True)
    )

    html = _shell(
        title=subject,
        preheader=_template_string('receipt_preheader', L, email_strings),
        body_html=body_html,
        lang=L,
    )

    text_parts = [
        _html_to_text(_template_string('receipt_hi', L, email_strings).format(name=first_name)),
        "",
        _html_to_text(_template_string('receipt_body', L, email_strings).format(event=event_name)),
        "",
    ]
    if group_code:
        text_parts.extend([
            f"{_template_string('receipt_group_code_title', L, email_strings)}: {group_code}",
            _template_string('receipt_group_code_hint', L, email_strings),
            "",
        ])
    text_parts.extend([
        _template_string('receipt_closing', L, email_strings),
        "",
        f"— {_s(L, 'powered_by')}",
        "",
    ])
    text = "\n".join(text_parts)

    return send_email(to_email, subject, html, text)


# Backwards-compat alias — callsites in app/api/participants.py use this name.
def send_registration_receipt(
    to_email: str, first_name: str, event_name: str, group_code: str | None = None, lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    return send_registration_confirmed(to_email, first_name, event_name, group_code, lang, email_strings)


def _send_simple_transactional_email(
    to_email: str,
    event_name: str,
    first_name: str,
    kind: str,
    lang: str,
    email_strings: dict[str, str] | None,
    **values: str | int,
) -> bool:
    L = lang if lang in EMAIL_STRINGS else 'en'
    template_values = {"event": event_name, "name": first_name, **values}
    subject = _template_string(f'{kind}_subject', L, email_strings).format(**template_values)
    greeting = _template_string(f'{kind}_hi', L, email_strings).format(**template_values)
    body = _template_string(f'{kind}_body', L, email_strings).format(**template_values)
    closing = _template_string(f'{kind}_closing', L, email_strings).format(**template_values)
    html = _shell(
        title=subject,
        preheader=_template_string(f'{kind}_preheader', L, email_strings).format(**template_values),
        body_html=(
            _logo()
            + _p(_safe_template_html(greeting))
            + _p(_safe_template_html(body))
            + _p(_safe_template_html(closing), muted=True)
        ),
        lang=L,
    )
    text = (
        f"{_html_to_text(greeting)}\n\n"
        f"{_html_to_text(body)}\n\n"
        f"{_html_to_text(closing)}\n\n"
        f"— {_s(L, 'powered_by')}\n"
    )
    return send_email(to_email, subject, html, text)


def send_payment_reminder_email(
    to_email: str,
    first_name: str,
    event_name: str,
    days_since_registration: int,
    lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    """Send an organiser-triggered reminder about an outstanding event fee."""
    return _send_simple_transactional_email(
        to_email, event_name, first_name, 'reminder', lang, email_strings,
        days=days_since_registration,
    )


def send_final_registration_confirmation_email(
    to_email: str,
    first_name: str,
    event_name: str,
    lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    """Send an organiser-triggered notice that a participant is confirmed."""
    return _send_simple_transactional_email(
        to_email, event_name, first_name, 'final_confirmation', lang, email_strings,
    )


def send_minor_form_email(
    to_email: str,
    first_name: str,
    event_name: str,
    upload_link: str,
    attachments: list[tuple[str, bytes, str]],
    lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    """Send an under-18 participant the consent form and private upload link."""
    L = lang if lang in EMAIL_STRINGS else 'en'
    template_values = {
        "event": event_name,
        "name": first_name,
        "upload_link": upload_link,
    }
    subject = _template_string(
        'minor_form_subject', L, email_strings
    ).format(**template_values)
    greeting = _template_string(
        'minor_form_hi', L, email_strings
    ).format(**template_values)
    body = _template_string(
        'minor_form_body', L, email_strings
    ).format(**template_values)
    closing = _template_string(
        'minor_form_closing', L, email_strings
    ).format(**template_values)
    escaped_link = _html_escape(upload_link, quote=True)
    body_html = _safe_template_html(body).replace(
        _html_escape(upload_link),
        f'<a href="{escaped_link}">{escaped_link}</a>',
    )
    html = _shell(
        title=subject,
        preheader=_template_string(
            'minor_form_preheader', L, email_strings
        ).format(**template_values),
        body_html=(
            _logo()
            + _p(_safe_template_html(greeting))
            + _p(body_html)
            + _p(_safe_template_html(closing), muted=True)
        ),
        lang=L,
    )
    text = (
        f"{_html_to_text(greeting)}\n\n"
        f"{_html_to_text(body)}\n\n"
        f"{_html_to_text(closing)}\n\n"
        f"— {_s(L, 'powered_by')}\n"
    )
    return send_email(
        to_email,
        subject,
        html,
        text,
        attachments=attachments,
    )


def send_registration_cancellation_email(
    to_email: str,
    first_name: str,
    event_name: str,
    lang: str = 'en',
    email_strings: dict[str, str] | None = None,
) -> bool:
    """Notify a participant when an organiser removes their registration."""
    return _send_simple_transactional_email(
        to_email, event_name, first_name, 'cancellation', lang, email_strings,
    )


def _safe_template_html(value: str) -> str:
    """Escape editable copy while retaining bold emphasis and line breaks."""
    escaped = _html_escape(value)
    escaped = escaped.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
    return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")

def send_password_reset_email(to_email: str, full_name: str, reset_url: str) -> bool:
    """Password-reset email. English only — admin/staff-facing. v0.70's
    translation overhaul may broaden this."""
    subject = "Reset your Moimio password"
    raw_first = full_name.split()[0] if full_name else "there"
    safe_first = _html_escape(raw_first)
    safe_url = _html_escape(reset_url, quote=True)

    body_html = (
        _logo()
        + _p(f"Hi {safe_first},")
        + _p("We received a request to reset your Moimio password. Click below to choose a new one.")
        + _button(reset_url, "Reset password")
        + _p("This link expires in 30 minutes.", muted=True, size="13px")
        + _p("If you didn't request a password reset, you can safely ignore this email — your password won't change.", muted=True, size="13px")
        + _hairline()
        + _p("If the button above doesn't work, copy and paste this link into your browser:", muted=True, size="12px")
        + f'<p style="margin: 0 0 4px 0; font-family: {_FONT_STACK}; '
          f'font-size: 12px; line-height: 1.5; word-break: break-all;">'
          f'<a href="{safe_url}" class="logo-accent" style="color: {_LIGHT_ACCENT}; '
          f'text-decoration: underline;">{_html_escape(reset_url)}</a></p>'
    )

    html = _shell(
        title=subject,
        preheader="Reset your Moimio password — link expires in 30 minutes.",
        body_html=body_html,
        lang='en',
    )

    text = (
        f"Hi {raw_first},\n\n"
        f"We received a request to reset your Moimio password.\n"
        f"Visit this link to choose a new one:\n\n"
        f"{reset_url}\n\n"
        f"This link expires in 30 minutes.\n"
        f"If you didn't request a password reset, you can ignore this email — your password won't change.\n\n"
        f"— Powered by Moimio\n"
    )

    return send_email(to_email, subject, html, text)


def render_smtp_test_email(
    event_name: str, from_name: str, reply_to: str, smtp_host: str, smtp_port: int
) -> tuple[str, str, str]:
    """Render the SMTP self-test email. Returns (subject, html, text).

    v0.61b: extracted from app/api/events.py so the test email uses the
    same shell as every other email we send. Called from the test-email
    endpoint."""
    subject = f"Moimio SMTP test — {event_name}"

    safe_event = _html_escape(event_name)
    safe_from = _html_escape(from_name)
    safe_reply = _html_escape(reply_to) if reply_to else '<span style="opacity:0.6;">(not set)</span>'
    safe_host = _html_escape(f"{smtp_host}:{smtp_port}")

    body_html = (
        _logo()
        + _p("<strong>SMTP test</strong>")
        + _p(f"This is a test email from <strong>{safe_event}</strong>. "
             f"If you're reading this, your email configuration is working.")
        + _hairline()
        + f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
          f'style="margin: 0 0 8px 0; font-family: {_FONT_STACK}; font-size: 12px; line-height: 1.6;">'
          f'<tr><td class="text-subtle" style="color: {_LIGHT_TEXT_SUBTLE}; padding-right: 12px; vertical-align: top;">Sent from</td>'
          f'<td class="text-muted" style="color: {_LIGHT_TEXT_MUTED};">{safe_from}</td></tr>'
          f'<tr><td class="text-subtle" style="color: {_LIGHT_TEXT_SUBTLE}; padding-right: 12px; vertical-align: top;">Reply-to</td>'
          f'<td class="text-muted" style="color: {_LIGHT_TEXT_MUTED};">{safe_reply}</td></tr>'
          f'<tr><td class="text-subtle" style="color: {_LIGHT_TEXT_SUBTLE}; padding-right: 12px; vertical-align: top;">SMTP server</td>'
          f'<td class="text-muted" style="color: {_LIGHT_TEXT_MUTED};">{safe_host}</td></tr>'
          f'</table>'
    )

    html = _shell(
        title=subject,
        preheader="SMTP configuration test — your email is working.",
        body_html=body_html,
        lang='en',
    )

    text = (
        f"SMTP test\n\n"
        f"This is a test email from {event_name}.\n"
        f"If you're reading this, your email configuration is working.\n\n"
        f"Sent from:   {from_name}\n"
        f"Reply-to:    {reply_to or '(not set)'}\n"
        f"SMTP server: {smtp_host}:{smtp_port}\n\n"
        f"— Powered by Moimio\n"
    )

    return subject, html, text
