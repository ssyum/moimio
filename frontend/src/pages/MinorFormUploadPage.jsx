import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { minorForms as minorFormsApi } from '../services/api';
import { useI18n } from '../hooks/useI18n';

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 2;
const MAX_TOTAL_BYTES = 18 * 1024 * 1024;

export default function MinorFormUploadPage() {
  const { token } = useParams();
  const { t } = useI18n();
  const inputRef = useRef(null);
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    minorFormsApi.getPublicUpload(token)
      .then(data => { if (active) setInfo(data); })
      .catch(err => { if (active) setError(err); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [token]);

  const handleUpload = async (event) => {
    event.preventDefault();
    const files = Array.from(inputRef.current?.files || []);
    if (!files.length || uploading) return;
    if (files.length !== MAX_FILES) {
      setError({ i18nKey: 'errors.minor_form.submission_file_count' });
      return;
    }
    if (files.some(file => !file.name.toLowerCase().endsWith('.pdf'))) {
      setError({ i18nKey: 'errors.minor_form.pdf_only' });
      return;
    }
    if (files.some(file => file.size > MAX_FILE_BYTES)) {
      setError({ i18nKey: 'errors.minor_form.file_too_large' });
      return;
    }
    if (files.reduce((total, file) => total + file.size, 0) > MAX_TOTAL_BYTES) {
      setError({ i18nKey: 'errors.minor_form.submission_total_too_large' });
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const result = await minorFormsApi.uploadPublicSubmission(token, files);
      setInfo(current => ({ ...current, uploaded: true, files: result.files }));
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      setError(err);
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--app-bg)' }}>
      <section className="card-surface-solid w-full max-w-lg rounded-2xl p-6 space-y-4"
        style={{ border: '1px solid var(--card-border)' }}>
        <h1 className="font-heading font-bold text-xl" style={{ color: 'var(--text-primary)' }}>
          {t('minor_form.upload_title')}
        </h1>
        {loading ? (
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{t('common.loading')}</p>
        ) : error && !info ? (
          <p role="alert" className="text-sm" style={{ color: 'var(--alert-burgundy)' }}>
            {error.i18nKey ? t(error.i18nKey) : t('minor_form.upload_error')}
          </p>
        ) : info && (
          <>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              {t('minor_form.upload_intro', { name: info.participant_name, event: info.event_name })}
            </p>
            {info.uploaded && (
              <p role="status" className="text-sm font-semibold" style={{ color: 'var(--success-color)' }}>
                {t('minor_form.upload_complete', {
                  count: info.files?.length || 0,
                  filenames: info.files?.join(', ') || '',
                })}
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm" style={{ color: 'var(--alert-burgundy)' }}>
                {error.i18nKey ? t(error.i18nKey) : t('minor_form.upload_error')}
              </p>
            )}
            <form onSubmit={handleUpload} className="space-y-3">
              <label className="block text-sm" style={{ color: 'var(--text-primary)' }}>
                {t('minor_form.upload_choose')}
                <input ref={inputRef} type="file" accept="application/pdf,.pdf" multiple required disabled={uploading}
                  className="block mt-2 text-sm" />
              </label>
              <p className="text-xs" style={{ color: 'var(--text-subtle)' }}>
                {t('minor_form.upload_limit')}
              </p>
              <button type="submit" disabled={uploading}
                className="text-sm font-semibold px-4 py-2 rounded-card bg-steel-blue text-white disabled:opacity-50">
                {uploading ? t('common.saving') : t('minor_form.upload_submit')}
              </button>
            </form>
          </>
        )}
      </section>
    </main>
  );
}
