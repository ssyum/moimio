import { useEffect, useState } from 'react';
import { email as emailApi, workspaceSettings as workspaceSettingsApi } from '../services/api';
import { useI18n } from '../hooks/useI18n';
import { useToast } from '../hooks/useToast';
import TranslatedError from './TranslatedError';

const LANGUAGES = [
  ['en', 'English'],
  ['de', 'Deutsch'],
  ['ko', '한국어'],
  ['es', 'Español'],
  ['pt-BR', 'Português (BR)'],
  ['fr', 'Français'],
];

const FIELDS = {
  confirmation: [
    ['confirm_subject', 'subject'],
    ['confirm_preheader', 'preheader'],
    ['confirm_hi', 'greeting'],
    ['confirm_body', 'body'],
    ['confirm_button', 'button'],
    ['confirm_fallback_pre', 'fallback'],
    ['confirm_footer', 'footer'],
  ],
  receipt: [
    ['receipt_subject', 'subject'],
    ['receipt_preheader', 'preheader'],
    ['receipt_hi', 'greeting'],
    ['receipt_body', 'body'],
    ['receipt_group_code_title', 'group_title'],
    ['receipt_group_code_hint', 'group_hint'],
    ['receipt_closing', 'closing'],
  ],
  minor_form: [
    ['minor_form_subject', 'subject'],
    ['minor_form_preheader', 'preheader'],
    ['minor_form_hi', 'greeting'],
    ['minor_form_body', 'body'],
    ['minor_form_closing', 'closing'],
  ],
  final_confirmation: [
    ['final_confirmation_subject', 'subject'],
    ['final_confirmation_preheader', 'preheader'],
    ['final_confirmation_hi', 'greeting'],
    ['final_confirmation_body', 'body'],
    ['final_confirmation_closing', 'closing'],
  ],
  reminder: [
    ['reminder_subject', 'subject'],
    ['reminder_preheader', 'preheader'],
    ['reminder_hi', 'greeting'],
    ['reminder_body', 'body'],
    ['reminder_closing', 'closing'],
  ],
  cancellation: [
    ['cancellation_subject', 'subject'],
    ['cancellation_preheader', 'preheader'],
    ['cancellation_hi', 'greeting'],
    ['cancellation_body', 'body'],
    ['cancellation_closing', 'closing'],
  ],
};

const TEXTAREA_FIELDS = new Set([
  'confirm_body', 'confirm_fallback_pre', 'confirm_footer',
  'receipt_body', 'receipt_group_code_hint', 'receipt_closing',
  'minor_form_body', 'minor_form_closing',
  'final_confirmation_body',
  'reminder_body', 'reminder_closing', 'cancellation_body', 'cancellation_closing',
]);

export default function EmailTemplatesPanel({ eventId }) {
  const { t } = useI18n();
  const { showToast, ToastHost } = useToast();
  const [templates, setTemplates] = useState({});
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    workspaceSettingsApi.getEmailTemplates()
      .then(data => {
        if (!cancelled) {
          setTemplates(data.templates);
          setLoaded(true);
        }
      })
      .catch(err => {
        if (!cancelled) setLoadError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const updateField = (language, field, value) => {
    setTemplates(current => ({
      ...current,
      [language]: { ...current[language], [field]: value },
    }));
    setSaved(false);
    setError(null);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (saving || loading || !loaded) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const data = await workspaceSettingsApi.updateEmailTemplates(templates);
      setTemplates(data.templates);
      setSaved(true);
      showToast(t('workspace.email.saved'), 'success');
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleTestEmail = async () => {
    if (testing) return;
    setTesting(true);
    setError(null);
    try {
      await emailApi.test(eventId);
      showToast(t('workspace.email.test_sent'), 'success');
    } catch (err) {
      setError(err);
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="mt-5 space-y-3">
      <header className="px-1">
        <h3 className="font-heading font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
          {t('workspace.email.title')}
        </h3>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          {t('workspace.email.help')}
        </p>
      </header>

      <TranslatedError err={loadError || error} variant="compact" />

      <EmailTemplateSection
        kind="receipt"
        templates={templates}
        loading={loading || !loaded}
        saving={saving}
        saved={saved}
        onChange={updateField}
        onSave={handleSave}
        onTest={handleTestEmail}
        testing={testing}
      />
      <EmailTemplateSection
        kind="confirmation"
        templates={templates}
        loading={loading || !loaded}
        saving={saving}
        saved={saved}
        onChange={updateField}
        onSave={handleSave}
      />
      <EmailTemplateSection
        kind="minor_form"
        templates={templates}
        loading={loading || !loaded}
        saving={saving}
        saved={saved}
        onChange={updateField}
        onSave={handleSave}
      />
      <EmailTemplateSection
        kind="final_confirmation"
        templates={templates}
        loading={loading || !loaded}
        saving={saving}
        saved={saved}
        onChange={updateField}
        onSave={handleSave}
      />
      <EmailTemplateSection
        kind="reminder"
        templates={templates}
        loading={loading || !loaded}
        saving={saving}
        saved={saved}
        onChange={updateField}
        onSave={handleSave}
      />
      <EmailTemplateSection
        kind="cancellation"
        templates={templates}
        loading={loading || !loaded}
        saving={saving}
        saved={saved}
        onChange={updateField}
        onSave={handleSave}
      />
      <ToastHost />
    </section>
  );
}

function EmailTemplateSection({
  kind, templates, loading, saving, saved, onChange, onSave, onTest, testing,
}) {
  const { t } = useI18n();
  const [language, setLanguage] = useState('en');
  const inputClass = 'w-full rounded-card border bg-[var(--app-bg)] border-[var(--card-border)] text-[var(--text-primary)] px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--io-accent)]';
  const currentTemplates = templates[language] || {};

  return (
    <details
      className="card-surface-solid rounded-2xl overflow-hidden"
      style={{ border: '1px solid var(--card-border)' }}
    >
      <summary
        className="cursor-pointer list-none px-4 py-3 font-heading font-semibold text-sm"
        style={{ color: 'var(--text-primary)' }}
      >
        {t(`workspace.email.${kind}`)}
        <span className="float-right text-xs" aria-hidden="true">⌄</span>
      </summary>
      <form
        className="p-4 space-y-4"
        onSubmit={onSave}
        style={{ borderTop: '1px solid var(--card-border)' }}
      >
        <label className="block text-xs font-semibold sm:max-w-xs" style={{ color: 'var(--text-muted)' }}>
          {t('workspace.email.language')}
          <select
            value={language}
            onChange={e => setLanguage(e.target.value)}
            disabled={loading || saving}
            className={`${inputClass} mt-1`}
          >
            {LANGUAGES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </label>

        {FIELDS[kind].map(([field, label]) => (
          <label key={field} className="block text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
            {t(`workspace.email.field.${label}`)}
            {TEXTAREA_FIELDS.has(field) ? (
              <textarea
                rows={field.endsWith('_body') ? 3 : 2}
                maxLength={2000}
                value={currentTemplates[field] || ''}
                onChange={e => onChange(language, field, e.target.value)}
                disabled={loading || saving}
                className={`${inputClass} mt-1 resize-y`}
              />
            ) : (
              <input
                type="text"
                maxLength={2000}
                value={currentTemplates[field] || ''}
                onChange={e => onChange(language, field, e.target.value)}
                disabled={loading || saving}
                className={`${inputClass} mt-1`}
              />
            )}
          </label>
        ))}

        <div className="flex items-center gap-3">
          {onTest && (
            <button
              type="button"
              onClick={onTest}
              disabled={testing || saving}
              className="text-sm font-semibold px-4 py-2 rounded-card border border-[var(--card-border)] hover:bg-black/5 dark:hover:bg-white/10 transition-colors disabled:opacity-60 disabled:cursor-wait"
              style={{ color: 'var(--text-primary)' }}
            >
              {testing ? t('workspace.email.testing') : t('workspace.email.test')}
            </button>
          )}
          <button
            type="submit"
            disabled={loading || saving}
            className="text-sm font-semibold px-4 py-2 rounded-card bg-steel-blue text-white hover:bg-steel-blue-700 transition-colors disabled:opacity-60 disabled:cursor-wait"
          >
            {saving ? t('workspace.email.saving') : t('common.save')}
          </button>
          {saved && (
            <span className="text-sm" role="status" style={{ color: 'var(--text-muted)' }}>
              {t('workspace.email.saved')}
            </span>
          )}
        </div>
      </form>
    </details>
  );
}
