import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MinorFormUploadPage from './MinorFormUploadPage';
import { minorForms } from '../services/api';

vi.mock('../services/api', () => ({
  minorForms: {
    getPublicUpload: vi.fn(),
    uploadPublicSubmission: vi.fn(),
  },
}));

vi.mock('../hooks/useI18n', () => ({
  useI18n: () => ({ t: key => key }),
}));

const renderPage = () => render(
  <MemoryRouter initialEntries={['/minor-form-upload/private-token']}>
    <Routes>
      <Route path="/minor-form-upload/:token" element={<MinorFormUploadPage />} />
    </Routes>
  </MemoryRouter>,
);

describe('MinorFormUploadPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    minorForms.getPublicUpload.mockResolvedValue({
      participant_name: 'Sam Example',
      event_name: 'Gathering',
      uploaded: false,
    });
    minorForms.uploadPublicSubmission.mockResolvedValue({ uploaded: true });
  });

  it('uploads the selected PDF through its private token link', async () => {
    renderPage();
    const input = await screen.findByLabelText('minor_form.upload_choose');
    const file = new File(['%PDF-1.7'], 'signed.pdf', { type: 'application/pdf' });
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(minorForms.uploadPublicSubmission).toHaveBeenCalledWith(
        'private-token',
        file,
      );
    });
    expect(await screen.findByRole('status')).toHaveTextContent('minor_form.upload_complete');
  });

  it('shows the API error when the upload link is expired', async () => {
    minorForms.getPublicUpload.mockRejectedValue({
      i18nKey: 'errors.minor_form.link_expired',
    });
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'errors.minor_form.link_expired',
    );
    expect(screen.queryByLabelText('minor_form.upload_choose')).not.toBeInTheDocument();
  });
});
