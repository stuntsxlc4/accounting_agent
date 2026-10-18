import { notifications } from '@mantine/notifications'
import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage, type Job } from './api'

/**
 * Stan operacji w tle danego rodzaju. Po powrocie na ekran wznawia
 * wyświetlanie trwającej operacji.
 */
export function useJob<T>(kind: string, onDone: (job: Job<T>) => void) {
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .runningJob()
      .then(({ job }) => job?.kind === kind && setJobId(job.id))
      .catch(() => undefined)
  }, [kind])

  const start = async (submit: () => Promise<{ job_id: string }>) => {
    setError(null)
    try {
      setJobId((await submit()).job_id)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Nie można rozpocząć', message: errorMessage(e) })
    }
  }

  const finished = useCallback(
    (job: Job<T>) => {
      setJobId(null)
      if (job.status === 'error') setError(job.error)
      onDone(job)
    },
    [onDone],
  )

  return { jobId, running: jobId !== null, error, clearError: () => setError(null), start, finished }
}
