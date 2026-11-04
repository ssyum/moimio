import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import EmailTemplatesPanel from './EmailTemplatesPanel';
import { email, workspaceSettings } from '../services/api';

vi.mock('../services/api', () => ({
  email: { test: vi.fn() },
  workspaceSettings: {
    getEmailTemplates: vi.fn(),
    updateEmailTemplates: vi.fn(),
  },
}));

vi.mock('../hooks/useI18n', () => ({
  useI18n: () => ({ t: key => key }),
}));

vi.mock('../hooks/useToast', () => ({
  useToast: () => ({ showToast: vi.fn(), ToastHost: () => null }),
}));

vi.mock('./TranslatedError', () => ({ default: () => null }));

const templates = {
  en: {
    confirm_subject: 'Confirm {event}',
    confirm_preheader: 'Confirm preview',
    confirm_hi: 'Hi {name}',
    confirm_body: 'Confirm {event}',
    confirm_button: 'Confirm',
    confirm_fallback_pre: 'Copy the link',
    confirm_footer: 'Ignore if not you',
    receipt_subject: 'Registered for {event}',
    receipt_preheader: 'Receipt preview',
    receipt_hi: 'Hello {name}',
    receipt_body: 'Welcome to <strong>{event}</strong>',
    receipt_group_code_title: 'Group code',
    receipt_group_code_hint: 'Share your group code',
    receipt_closing: 'See you soon',
    reminder_subject: 'Payment reminder for {event}',
    reminder_preheader: 'A reminder',
    reminder_hi: 'Hi {name}',
    reminder_body: 'Please pay for {event}; {days} days have passed.',
    reminder_closing: 'Ignore if paid',
    cancellation_subject: 'Cancelled: {event}',
    cancellation_preheader: 'Registration update',
    cancellation_hi: 'Hi {name}',
    cancellation_body: 'Your registration for {event} was cancelled.',
    cancellation_closing: 'Contact the organisers',
  },
};

describe('EmailTemplatesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceSettings.getEmailTemplates.mockResolvedValue({ templates });
    workspaceSettings.updateEmailTemplates.mockImplementation(async value => ({ templates: value }));
    email.test.mockResolvedValue({ detail: 'sent' });
  });

  it('keeps both email editors separate, collapsible, editable, and testable', async () => {
    render(<EmailTemplatesPanel eventId="event-1" />);

    const receiptSummary = screen.getByText('workspace.email.receipt');
    const confirmationSummary = screen.getByText('workspace.email.confirmation');
    const reminderSummary = screen.getByText('workspace.email.reminder');
    const cancellationSummary = screen.getByText('workspace.email.cancellation');
    const receipt = receiptSummary.closest('details');
    const confirmation = confirmationSummary.closest('details');
    const reminder = reminderSummary.closest('details');
    const cancellation = cancellationSummary.closest('details');
    expect(receipt.open).toBe(false);
    expect(confirmation.open).toBe(false);
    expect(reminder.open).toBe(false);
    expect(cancellation.open).toBe(false);

    fireEvent.click(receiptSummary);
    fireEvent.click(confirmationSummary);

    const receiptBody = await within(receipt).findByLabelText('workspace.email.field.body');
    expect(receiptBody.value).toBe('Welcome to <strong>{event}</strong>');
    fireEvent.change(receiptBody, { target: { value: 'Thanks for joining {event}' } });
    fireEvent.click(within(receipt).getByRole('button', { name: 'common.save' }));

    await waitFor(() => {
      expect(workspaceSettings.updateEmailTemplates).toHaveBeenCalledWith(
        expect.objectContaining({
          en: expect.objectContaining({ receipt_body: 'Thanks for joining {event}' }),
        }),
      );
    });

    const confirmationBody = within(confirmation).getByLabelText('workspace.email.field.body');
    expect(confirmationBody.value).toBe('Confirm {event}');
    fireEvent.change(confirmationBody, { target: { value: 'Please confirm {event}' } });
    fireEvent.click(within(confirmation).getByRole('button', { name: 'common.save' }));

    await waitFor(() => {
      expect(workspaceSettings.updateEmailTemplates).toHaveBeenLastCalledWith(
        expect.objectContaining({
          en: expect.objectContaining({ confirm_body: 'Please confirm {event}' }),
        }),
      );
    });

    fireEvent.click(reminderSummary);
    const reminderBody = within(reminder).getByLabelText('workspace.email.field.body');
    expect(reminderBody.value).toBe('Please pay for {event}; {days} days have passed.');
    fireEvent.change(reminderBody, { target: { value: 'Payment for {event} is due after {days} days.' } });
    fireEvent.click(within(reminder).getByRole('button', { name: 'common.save' }));
    await waitFor(() => {
      expect(workspaceSettings.updateEmailTemplates).toHaveBeenLastCalledWith(
        expect.objectContaining({
          en: expect.objectContaining({
            reminder_body: 'Payment for {event} is due after {days} days.',
          }),
        }),
      );
    });

    fireEvent.click(cancellationSummary);
    expect(within(cancellation).getByLabelText('workspace.email.field.body').value)
      .toBe('Your registration for {event} was cancelled.');

    fireEvent.click(within(receipt).getByRole('button', { name: 'workspace.email.test' }));
    await waitFor(() => expect(email.test).toHaveBeenCalledWith('event-1'));
  });
});
