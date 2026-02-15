'use client';

import {
  EnvelopeIcon,
  PhoneIcon,
  BuildingOfficeIcon,
  TagIcon,
} from '@heroicons/react/24/outline';
import type { Contact } from '../../../types/structured-data';

interface ContactCardProps {
  contact: Contact;
  index?: number;
  compact?: boolean;
}

/**
 * Get initials from name for avatar.
 */
function getInitials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((n) => n[0])
    .join('')
    .toUpperCase();
}

export function ContactCard({
  contact,
  index,
  compact = false,
}: ContactCardProps) {
  const initials = contact.name ? getInitials(contact.name) : '?';

  if (compact) {
    return (
      <div className="flex items-center gap-3 p-3 rounded-lg bg-[var(--muted)]/50 border border-[var(--border)] hover:border-[oklch(0.65_0.2_200/0.3)] transition-colors">
        <div className="w-8 h-8 rounded-full bg-[oklch(0.65_0.2_200/0.15)] text-[oklch(0.65_0.2_200)] text-xs font-medium flex items-center justify-center">
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--foreground)] truncate">
            {contact.name}
          </p>
          {contact.email && (
            <p className="text-xs text-[var(--muted-foreground)] truncate">
              {contact.email}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-lg bg-[var(--muted)]/50 border border-[var(--border)] hover:border-[oklch(0.65_0.2_200/0.3)] transition-colors">
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="w-10 h-10 rounded-full bg-[oklch(0.65_0.2_200/0.15)] text-[oklch(0.65_0.2_200)] text-sm font-medium flex items-center justify-center flex-shrink-0">
          {initials}
        </div>

        <div className="flex-1 min-w-0">
          {/* Name */}
          <h4 className="text-sm font-medium text-[var(--foreground)]">
            {contact.name || 'Unknown'}
          </h4>

          {/* Title and company */}
          {(contact.title || contact.company) && (
            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
              {contact.title}
              {contact.title && contact.company && ' at '}
              {contact.company}
            </p>
          )}

          {/* Contact info */}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--muted-foreground)]">
            {contact.email && (
              <a
                href={`mailto:${contact.email}`}
                className="inline-flex items-center gap-1 hover:text-[oklch(0.65_0.2_200)] transition-colors"
              >
                <EnvelopeIcon className="w-3.5 h-3.5" />
                <span className="truncate max-w-[180px]">{contact.email}</span>
              </a>
            )}

            {contact.phone && (
              <a
                href={`tel:${contact.phone}`}
                className="inline-flex items-center gap-1 hover:text-[oklch(0.65_0.2_200)] transition-colors"
              >
                <PhoneIcon className="w-3.5 h-3.5" />
                {contact.phone}
              </a>
            )}

            {contact.company && !contact.title && (
              <span className="inline-flex items-center gap-1">
                <BuildingOfficeIcon className="w-3.5 h-3.5" />
                {contact.company}
              </span>
            )}
          </div>

          {/* Tags */}
          {contact.tags && contact.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {contact.tags.slice(0, 3).map((tag, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] bg-[var(--muted)] rounded text-[var(--muted-foreground)]"
                >
                  <TagIcon className="w-2.5 h-2.5" />
                  {tag}
                </span>
              ))}
              {contact.tags.length > 3 && (
                <span className="text-[10px] text-[var(--muted-foreground)]">
                  +{contact.tags.length - 3}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
