import { Alert, Button, Card, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconAlertTriangle, IconFileText, IconPlugConnected } from '@tabler/icons-react'
import { useCallback } from 'react'
import type { Job, Status } from '../api'
import { api, errorMessage } from '../api'
import { JobError, JobProgress } from '../components/JobProgress'
import { formatDate } from '../format'
import { useJob } from '../useJob'
import { PageHeader } from './PageHeader'

interface Props {
  status: Status
  onChanged: () => void
}

export function Settings({ status, onChanged }: Props) {
  const onDone = useCallback(
    (job: Job<{ message: string }>) => {
      if (job.status === 'done') {
        notifications.show({ color: 'green', title: 'Połączenie z KSeF działa', message: job.result?.message })
      }
      onChanged()
    },
    [onChanged],
  )
  const job = useJob('test', onDone)

  const openLogs = () =>
    api.open('logs').catch((e) => notifications.show({ color: 'red', message: errorMessage(e) }))

  return (
    <>
      <PageHeader title="Ustawienia" subtitle="Połączenie z KSeF i foldery na dokumenty">
        <Button variant="default" leftSection={<IconFileText size={18} />} onClick={openLogs}>
          Dziennik zdarzeń
        </Button>
        <Button
          leftSection={<IconPlugConnected size={18} />}
          onClick={() => job.start(() => api.testConnection())}
          loading={job.running}
          disabled={!status.configured}
        >
          Sprawdź połączenie z KSeF
        </Button>
      </PageHeader>

      <JobError error={job.error} onClose={job.clearError} />
      {job.jobId ? <JobProgress jobId={job.jobId} onFinished={job.finished} /> : null}

      {!status.configured ? (
        <Alert color="orange" icon={<IconAlertTriangle />} title="Brak konfiguracji" mb="lg">
          {status.error}
        </Alert>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" mt="md">
          <Card withBorder padding="lg">
            <Text fw={600} mb="sm">
              Firma i KSeF
            </Text>
            <Stack gap="xs">
              <Field label="NIP" value={status.nip} />
              <Field label="Środowisko KSeF" value={status.environment === 'prod' ? 'produkcyjne' : status.environment} />
              <Field label="Certyfikat" value={status.certificate?.name} />
              <Field label="Certyfikat ważny do" value={formatDate(status.certificate?.valid_to)} />
            </Stack>
          </Card>
          <Card withBorder padding="lg">
            <Text fw={600} mb="sm">
              Foldery
            </Text>
            <Stack gap="xs">
              <Field label="Faktury zakupowe" value={status.invoices_dir} />
              <Field label="Wyciągi bankowe" value={status.statements_dir} />
            </Stack>
            <Group mt="md">
              <Text size="xs" c="dimmed">
                W każdym folderze aplikacja tworzy podfoldery miesięcy, np. „Sierpień 2026”.
              </Text>
            </Group>
          </Card>
        </SimpleGrid>
      )}
    </>
  )
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="sm" style={{ wordBreak: 'break-all' }}>
        {value || '—'}
      </Text>
    </div>
  )
}
