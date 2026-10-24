import { Alert, Button, Card, Center, FileInput, Group, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCertificate, IconCircleCheck, IconKey } from '@tabler/icons-react'
import { useCallback, useState } from 'react'
import type { Job, Status } from '../api'
import { api, errorMessage } from '../api'
import { JobError, JobProgress } from '../components/JobProgress'
import { useJob } from '../useJob'

interface Props {
  status: Status
  onDone: () => void
  /** Zmiana certyfikatu z Ustawień; bez tego kreator pierwszego uruchomienia. */
  onCancel?: () => void
}

/** Kreator: NIP firmy, pliki certyfikatu KSeF i hasło do klucza, a na końcu test logowania. */
export function Setup({ status, onDone, onCancel }: Props) {
  const [nip, setNip] = useState(status.nip ?? '')
  const [certificate, setCertificate] = useState<File | null>(null)
  const [key, setKey] = useState<File | null>(null)
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const onTested = useCallback(
    (job: Job<{ message: string }>) => {
      if (job.status !== 'done') return
      notifications.show({ color: 'green', title: 'Połączenie z KSeF działa', message: job.result?.message })
      onDone()
    },
    [onDone],
  )
  const test = useJob('test', onTested)

  const submit = async () => {
    if (!certificate || !key) return
    setSaving(true)
    setError(null)
    try {
      await api.setup(nip, password, certificate, key)
      setSaved(true)
      setPassword('')
      await test.start(() => api.testConnection())
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const busy = saving || test.running
  const ready = nip.trim() !== '' && certificate !== null && key !== null && password !== ''
  // Ustawienia zapisane, ale logowanie się nie udało (np. brak uprawnień albo KSeF nie odpowiada)
  const failed = saved && test.error !== null
  const retry = () => test.start(() => api.testConnection())

  return (
    <Center py="xl">
      <Card withBorder padding="xl" radius="md" w="100%" maw={620}>
        <Stack gap="lg">
          <div>
            <Title order={2}>{onCancel ? 'Zmiana certyfikatu KSeF' : 'Witaj w aplikacji Faktury KSeF'}</Title>
            <Text c="dimmed" mt={4}>
              {onCancel
                ? 'Wskaż pliki nowego certyfikatu. Aplikacja sprawdzi je i zaloguje się do KSeF.'
                : 'Zanim zaczniesz, połącz aplikację z KSeF. Potrzebne są pliki certyfikatu KSeF i hasło do niego.'}
            </Text>
          </div>

          <TextInput
            label="NIP firmy"
            description="Firma, której faktury zakupowe pobieramy z KSeF"
            placeholder="10 cyfr"
            value={nip}
            onChange={(e) => setNip(e.currentTarget.value)}
            disabled={busy}
          />
          <FileInput
            label="Plik certyfikatu"
            description="Plik .crt pobrany przy generowaniu certyfikatu w Aplikacji Podatnika KSeF"
            placeholder="Wybierz plik .crt"
            accept=".crt,.cer,.pem"
            leftSection={<IconCertificate size={18} />}
            value={certificate}
            onChange={setCertificate}
            clearable
            disabled={busy}
          />
          <FileInput
            label="Plik klucza prywatnego"
            description="Plik .key z tej samej pary co certyfikat"
            placeholder="Wybierz plik .key"
            accept=".key,.pem"
            leftSection={<IconKey size={18} />}
            value={key}
            onChange={setKey}
            clearable
            disabled={busy}
          />
          <PasswordInput
            label="Hasło do klucza"
            description="Hasło podane przy generowaniu certyfikatu. Zostanie zapisane w sejfie systemu."
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
            disabled={busy}
          />

          {error ? (
            <Alert color="red" title="Nie udało się zapisać" withCloseButton onClose={() => setError(null)}>
              {error}
            </Alert>
          ) : null}
          <JobError error={test.error} onClose={test.clearError} />
          {test.jobId ? <JobProgress jobId={test.jobId} onFinished={test.finished} /> : null}

          <Group justify="space-between">
            <Text size="xs" c="dimmed" maw={300}>
              Aplikacja kopiuje pliki certyfikatu do swoich danych. Potem możesz je usunąć z pendrive'a.
            </Text>
            <Group gap="sm">
              {onCancel ? (
                <Button variant="default" onClick={onCancel} disabled={busy}>
                  Anuluj
                </Button>
              ) : null}
              {failed ? (
                <Button variant="default" onClick={onDone}>
                  Przejdź do aplikacji
                </Button>
              ) : null}
              {failed && !ready ? (
                <Button leftSection={<IconCircleCheck size={18} />} onClick={retry} loading={busy}>
                  Sprawdź ponownie
                </Button>
              ) : (
                <Button leftSection={<IconCircleCheck size={18} />} onClick={submit} loading={busy} disabled={!ready}>
                  Zapisz i sprawdź połączenie
                </Button>
              )}
            </Group>
          </Group>
        </Stack>
      </Card>
    </Center>
  )
}
