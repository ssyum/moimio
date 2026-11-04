import { useEffect, useRef, useState } from 'react';
import { minorForms as minorFormsApi } from '../services/api';
import { useI18n } from '../hooks/useI18n';
import { useToast } from '../hooks/useToast';

const MAX_FILE_BYTES = 10 * 1024 * 1024;

export default function MinorFormTemplatePanel({ eventId }) {
  const { t } = useI18n();
  const { showToast } = useToast();
  const inputRef = useRef(null);
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    minorFormsApi.getTemplate(eventId)
      .then(data => { if (active) setTemplate(data); })
      .catch(error => { if (active) showToast(error, 'error'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [eventId, showToast]);

  const handleUpload = async (event) => {
    event.preventDefault();
    const file = inputRef.current?.files?.[0];
    if (!file || saving) return;
    if (!file.name.toLowerCase().endsWith('.pdf') || file.size > MAX_FILE_BYTES) {
      showToast(new Error(t(file.size > MAX_FILE_BYTES
        ? 'errors.minor_form.file_too_large'
        : 'errors.minor_form.pdf_only')), 'error');
      return;
    }
    setSaving(true);
    try {
      const saved = await minorFormsApi.uploadTemplate(eventId, file);
      setTemplate(saved);
      inputRef.current.value = '';
      showToast(t('minor_form.template_saved'), 'success');
    } catch (error) {
      showToast(error, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await minorFormsApi.deleteTemplate(eventId);
      setTemplate({ available: false, filename: null });
      showToast(t('minor_form.template_deleted'), 'success');
    } catch (error) {
      showToast(error, 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="card-surface-solid rounded-2xl p-4 mt-5 space-y-3"
      style={{ border: '1px solid var(--card-border)' }}
    >
      <div>
        <h3 className="font-heading font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
          {t('minor_form.template_title')}
        </h3>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          {t('minor_form.template_help')}
        </p>
      </div>
      {loading ? (
        <p className="text-xs" style={{ color: 'var(--text-subtle)' }}>{t('common.loading')}</p>
      ) : (
        <>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {template?.available
              ? t('minor_form.template_current', { filename: template.filename })
              : t('minor_form.template_missing')}
          </p>
          <form onSubmit={handleUpload} className="flex flex-wrap items-center gap-2">
            <input ref={inputRef} type="file" accept="application/pdf,.pdf" required={!template?.available}
              disabled={saving} className="text-xs max-w-full" />
            <button type="submit" disabled={saving}
              className="text-xs font-semibold px-3 py-1.5 rounded-card bg-steel-blue text-white disabled:opacity-50">
              {saving ? t('common.saving') : t('minor_form.template_upload')}
            </button>
            {template?.available && (
              <button type="button" disabled={saving} onClick={handleDelete}
                className="text-xs font-semibold px-3 py-1.5 rounded-card border border-[var(--card-border)] disabled:opacity-50"
                style={{ color: 'var(--alert-burgundy)' }}>
                {t('minor_form.template_remove')}
              </button>
            )}
          </form>
        </>
      )}
    </section>
  );
}
