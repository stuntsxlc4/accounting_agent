import { Alert, AppShell, Badge, Button, Center, Group, Loader, NavLink, Stack, Text, ThemeIcon, Title } from '@mantine/core'
import {
  IconAlertTriangle,
  IconBuildingBank,
  IconFileInvoice,
  IconLayoutDashboard,
  IconReceipt2,
  IconSettings,
} from '@tabler/icons-react'
import { useCallback, useEffect, useState } from 'react'
import { api, type Status } from './api'
import { Dashboard } from './pages/Dashboard'
import { Invoices } from './pages/Invoices'
import { Settings } from './pages/Settings'
import { Setup } from './pages/Setup'
import { Statements } from './pages/Statements'

export type Page = 'dashboard' | 'invoices' | 'statements' | 'settings'

const NAV: { page: Page; label: string; description: string; icon: typeof IconFileInvoice }[] = [
  { page: 'dashboard', label: 'Pulpit', description: 'Stan i szybkie akcje', icon: IconLayoutDashboard },
  { page: 'invoices', label: 'Faktury', description: 'Pobieranie z KSeF', icon: IconFileInvoice },
  { page: 'statements', label: 'Wyciągi i płatności', description: 'Porównanie z fakturami', icon: IconBuildingBank },
  { page: 'settings', label: 'Ustawienia', description: 'Certyfikat i foldery', icon: IconSettings },
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [status, setStatus] = useState<Status | null>(null)
  const [month, setMonth] = useState<string | null>(null)
  const [offline, setOffline] = useState(false)

  const loadStatus = useCallback(
    () =>
      api
        .status()
        .then((current) => {
          setStatus(current)
          setOffline(false)
          setMonth((m) => m ?? current.previous_month)
        })
        .catch(() => setOffline(true)),
    [],
  )

  useEffect(() => {
    api
      .status()
      .then((current) => {
        setStatus(current)
        setMonth(current.previous_month)
      })
      .catch(() => setOffline(true))
  }, [])

  const go = (target: Page, targetMonth?: string) => {
    if (targetMonth) setMonth(targetMonth)
    setPage(target)
  }

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 260, breakpoint: 0 }} padding="lg">
      <AppShell.Header>
        <Group h="100%" px="lg" justify="space-between">
          <Group gap="sm">
            <ThemeIcon size={34} radius="md">
              <IconReceipt2 size={20} />
            </ThemeIcon>
            <div>
              <Title order={4} lh={1.1}>
                Faktury KSeF
              </Title>
              <Text size="xs" c="dimmed">
                Ludna 2 · księgowość
              </Text>
            </div>
          </Group>
          {status?.configured ? (
            <Group gap="xs">
              <Text size="sm" c="dimmed">
                NIP {status.nip}
              </Text>
              <Badge variant="light" color={status.environment === 'prod' ? 'green' : 'orange'}>
                {status.environment === 'prod' ? 'KSeF produkcja' : `KSeF ${status.environment}`}
              </Badge>
            </Group>
          ) : null}
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        <Stack gap={4}>
          {NAV.map((item) => (
            <NavLink
              key={item.page}
              active={page === item.page}
              label={item.label}
              description={item.description}
              leftSection={<item.icon size={20} stroke={1.6} />}
              onClick={() => setPage(item.page)}
              disabled={status !== null && !status.configured}
              styles={{ root: { borderRadius: 'var(--mantine-radius-md)' } }}
            />
          ))}
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main bg="gray.0">
        {offline ? (
          <Center h="70%">
            <Alert color="red" icon={<IconAlertTriangle />} title="Brak połączenia z aplikacją" maw={520}>
              <Stack>
                <Text size="sm">Część aplikacji działająca w tle nie odpowiada. Spróbuj ponownie albo uruchom aplikację jeszcze raz.</Text>
                <Group>
                  <Button variant="light" color="red" onClick={loadStatus}>
                    Spróbuj ponownie
                  </Button>
                </Group>
              </Stack>
            </Alert>
          </Center>
        ) : !status || !month ? (
          <Center h="70%">
            <Loader />
          </Center>
        ) : !status.configured ? (
          <Setup status={status} onDone={loadStatus} />
        ) : (
          <>
            {page === 'dashboard' && <Dashboard status={status} go={go} />}
            {page === 'invoices' && <Invoices key={month} month={month} onMonthChange={setMonth} />}
            {page === 'statements' && <Statements key={month} month={month} onMonthChange={setMonth} />}
            {page === 'settings' && <Settings status={status} onChanged={loadStatus} />}
          </>
        )}
      </AppShell.Main>
    </AppShell>
  )
}
