import { useEffect, useRef, useState } from 'react';
import { minorForms as minorFormsApi } from '../services/api';
import { useI18n } from '../hooks/useI18n';
import { useToast } from '../hooks/useToast';

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_BYTES = 18 * 1024 * 1024;

export default function MinorFormTemplatePanel({ eventId }) {
  const { t } = useI18n();
  const { showToast } = useToast();
  const inputRef = useRef(null);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    minorFormsApi.getTemplate(eventId)
      .then(data => { if (active) setTemplates(data.files || []); })
      .catch(error => { if (active) showToast(error, 'error'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [eventId, showToast]);

  const handleUpload = async (event) => {
    event.preventDefault();
    const files = Array.from(inputRef.current?.files || []);
    if (!files.length || saving) return;
    const totalBytes = files.reduce((total, file) => total + file.size, 0);
    if (files.some(file => !file.name.toLowerCase().endsWith('.pdf'))) {
      showToast(new Error(t('errors.minor_form.pdf_only')), 'error');
      return;
    }
    if (files.some(file => file.size > MAX_FILE_BYTES) || totalBytes > MAX_TOTAL_BYTES) {
      showToast(new Error(t(
        totalBytes > MAX_TOTAL_BYTES
          ? 'errors.minor_form.total_too_large'
          : 'errors.minor_form.file_too_large',
      )), 'error');
      return;
    }
    setSaving(true);
    try {
      const saved = await minorFormsApi.uploadTemplate(eventId, files);
      setTemplates(current => [...current, ...saved.files]);
      inputRef.current.value = '';
      showToast(t('minor_form.template_saved'), 'success');
    } catch (error) {
      showToast(error, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (storageKey) => {
    if (saving) return;
    setSaving(true);
    try {
      await minorFormsApi.deleteTemplate(eventId, storageKey);
      setTemplates(current => current.filter(file => file.storage_key !== storageKey));
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
          {templates.length ? (
            <ul className="space-y-2" aria-label={t('minor_form.template_files')}>
              {templates.map(file => (
                <li key={file.storage_key} className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="min-w-0 break-all" style={{ color: 'var(--text-muted)' }}>
                    {file.filename}
                  </span>
                  <button type="button" disabled={saving}
                    onClick={() => handleDelete(file.storage_key)}
                    className="font-semibold hover:underline disabled:opacity-50"
                    style={{ color: 'var(--alert-burgundy)' }}>
                    {t('minor_form.template_remove')}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {t('minor_form.template_missing')}
            </p>
          )}
          <form onSubmit={handleUpload} className="flex flex-wrap items-center gap-2">
            <input ref={inputRef} type="file" accept="application/pdf,.pdf" multiple
              required={!templates.length}
              disabled={saving} className="text-xs max-w-full" />
            <button type="submit" disabled={saving}
              className="text-xs font-semibold px-3 py-1.5 rounded-card bg-steel-blue text-white disabled:opacity-50">
              {saving ? t('common.saving') : t('minor_form.template_upload')}
            </button>
          </form>
        </>
      )}
    </section>
  );
}
