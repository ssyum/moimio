import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MinorFormTemplatePanel from './MinorFormTemplatePanel';
import { minorForms } from '../services/api';

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock('../services/api', () => ({
  minorForms: {
    getTemplate: vi.fn(),
    uploadTemplate: vi.fn(),
    deleteTemplate: vi.fn(),
  },
}));

vi.mock('../hooks/useI18n', () => ({
  useI18n: () => ({ t: key => key }),
}));

vi.mock('../hooks/useToast', () => ({
  useToast: () => ({ showToast }),
}));

describe('MinorFormTemplatePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    minorForms.getTemplate.mockResolvedValue({
      available: true,
      files: [{ storage_key: 'consent-key', filename: 'consent.pdf' }],
    });
    minorForms.uploadTemplate.mockImplementation(async (_eventId, files) => ({
      available: true,
      files: files.map((file, index) => ({
        storage_key: `new-${index}`,
        filename: file.name,
      })),
    }));
    minorForms.deleteTemplate.mockResolvedValue(null);
  });

  it('uploads multiple PDFs and removes a selected template independently', async () => {
    const { container } = render(<MinorFormTemplatePanel eventId="event-1" />);
    await screen.findByText('consent.pdf');
    const input = container.querySelector('input[type="file"]');
    const consent = new File(['%PDF-1.7'], 'consent.pdf', { type: 'application/pdf' });
    const privacy = new File(['%PDF-1.7'], 'data privacy agreement.pdf', {
      type: 'application/pdf',
    });
    Object.defineProperty(input, 'files', { configurable: true, value: [consent, privacy] });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(minorForms.uploadTemplate).toHaveBeenCalledWith(
        'event-1',
        [consent, privacy],
      );
    });
    expect(await screen.findByText('data privacy agreement.pdf')).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'minor_form.template_remove' })[0]);
    await waitFor(() => {
      expect(minorForms.deleteTemplate).toHaveBeenCalledWith('event-1', 'consent-key');
    });
  });
});
