import { formatRegistrationDate, parseRegistrationDate } from '../utils/registrationDate';

export default function RegistrationDateInput({
  value,
  onChange,
  className,
  name,
  required = false,
  invalid = false,
  pickerLabel,
}) {
  const isoValue = parseRegistrationDate(value) || '';

  return (
    <div className="relative">
      <input
        type="text"
        inputMode="numeric"
        placeholder="DD.MM.YYYY"
        name={name}
        value={formatRegistrationDate(value)}
        onChange={event => onChange(event.target.value)}
        required={required}
        aria-invalid={invalid}
        className={`${className} pr-12`}
      />
      <span className="absolute inset-y-0 right-0 flex w-11 items-center justify-center pointer-events-none"
        aria-hidden="true">
        <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5 text-gray-500">
          <rect x="3" y="5" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
          <path d="M6.5 3.5v3M13.5 3.5v3M3 8.5h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </span>
      <input
        type="date"
        tabIndex={0}
        aria-label={pickerLabel}
        aria-invalid={invalid}
        value={isoValue}
        onChange={event => onChange(event.target.value)}
        className="absolute inset-y-0 right-0 w-11 cursor-pointer opacity-0"
      />
    </div>
  );
}
