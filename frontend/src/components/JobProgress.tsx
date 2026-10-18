import { Alert, Group, Loader, Paper, Progress, Stack, Text } from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { api, type Job } from '../api'

const POLL_MS = 700

interface Props<T> {
  jobId: string
  onFinished: (job: Job<T>) => void
}

/** Postęp zadania w tle (pobieranie z KSeF, porównanie). */
export function JobProgress<T>({ jobId, onFinished }: Props<T>) {
  const [job, setJob] = useState<Job<T> | null>(null)

  useEffect(() => {
    let active = true
    const tick = async () => {
      try {
        const current = await api.job<T>(jobId)
        if (!active) return
        setJob(current)
        if (current.status === 'running') setTimeout(tick, POLL_MS)
        else onFinished(current)
      } catch {
        if (active) setTimeout(tick, POLL_MS * 2)
      }
    }
    tick()
    return () => {
      active = false
    }
  }, [jobId, onFinished])

  if (job?.status === 'error') {
    return (
      <Alert color="red" icon={<IconAlertTriangle />} title="Operacja nie powiodła się">
        {job.error}
      </Alert>
    )
  }
  if (job?.status === 'done') return null

  const percent = job?.total ? Math.round(((job.done ?? 0) / job.total) * 100) : null
  return (
    <Paper withBorder p="md">
      <Stack gap="xs">
        <Group gap="sm">
          <Loader size="sm" />
          <Text fw={500}>{job?.message ?? 'Uruchamianie…'}</Text>
          {job?.total ? (
            <Text c="dimmed" size="sm">
              {job.done} z {job.total}
            </Text>
          ) : null}
        </Group>
        <Progress value={percent ?? 100} animated striped={percent === null} />
      </Stack>
    </Paper>
  )
}
