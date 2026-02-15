'use client';

import { useRouter } from 'next/navigation';
import { ExamplesMenu } from '../../components/ExamplesMenu';

export default function ExamplesPage() {
  const router = useRouter();

  return (
    <div className="h-full overflow-auto p-4">
      <ExamplesMenu onWorkflowCreated={() => router.push('/workflows')} />
    </div>
  );
}

