'use client';

import { Suspense } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import type { PublicTemplateResponse } from '@/types/version';

const TemplateGallery = dynamic(
  () => import('@/components/PublicGallery/TemplateGallery'),
  { ssr: false }
);

export default function PublicGalleryPage() {
  const router = useRouter();

  const handleCopySuccess = (template: PublicTemplateResponse) => {
    // Navigate to playground after successful copy
    router.push('/playground');
  };

  return (
    <div className="h-full overflow-auto p-6">
      <Suspense fallback={<div className="p-4">Loading templates...</div>}>
        <TemplateGallery onCopySuccess={handleCopySuccess} />
      </Suspense>
    </div>
  );
}
