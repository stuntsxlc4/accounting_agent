import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Timeline,
  Title,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconArrowRight,
  IconBuildingBank,
  IconCertificate,
  IconCircleCheck,
  IconCircleX,
  IconCloudDownload,
  IconFileInvoice,
  IconHistory,
  IconScale,
} from '@tabler/icons-react'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import type { Page } from '../App'
import { api, type HistoryItem, type Overview, type Status } from '../api'
import { CardSkeleton } from '../components/Loading'
import { PathLabel } from '../components/PathLabel'
import { formatDate, formatDateTime } from '../format'
import { PageHeader } from './PageHeader'

interface Props {
  status: Status
  go: (page: Page, month?: string) => void
}

const HISTORY_LABELS: Record<HistoryItem['kind'], string> = {
  download: 'Pobranie faktur',
  reconcile: 'Porównanie z wyciągami',
  test: 'Test połączenia',
}

export function Dashboard({ status, go }: Props) {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [history, setHistory] = useState<HistoryItem[] | null>(null)
  const month = status.previous_month
  const monthLabel = dayjs(`${month}-01`).format('MMMM YYYY')

  useEffect(() => {
    api.overview(month).then(setOverview).catch(() => setOverview(null))
    api.history().then(setHistory).catch(() => setHistory([]))
  }, [month])

  const cert = status.certificate!
  const certColor = cert.days_left < 30 ? 'red' : cert.days_left < 90 ? 'orange' : 'green'

  return (
    <>
      <PageHeader title="Pulpit" subtitle={<Text c="dimmed">{greeting()} Do rozliczenia jest {monthLabel}.</Text>} />

      {cert.days_left < 30 ? (
        <Alert color="red" icon={<IconCertificate />} title="Certyfikat KSeF wkrótce wygaśnie" mb="lg">
          <Stack gap="xs">
            <Text size="sm">
              Certyfikat jest ważny do {formatDate(cert.valid_to)}. Wygeneruj nowy w Aplikacji Podatnika KSeF i wskaż
              go w Ustawieniach.
            </Text>
            <Group>
              <Button size="xs" variant="light" color="red" onClick={() => go('settings')}>
                Przejdź do ustawień
              </Button>
            </Group>
          </Stack>
        </Alert>
      ) : null}

      {overview?.to_explain.length ? (
        <Alert color="red" icon={<IconAlertTriangle />} title="Faktury do wyjaśnienia" mb="lg">
          <Stack gap="xs">
            <Text size="sm">
              Te faktury nie zostały znalezione na wyciągach przez co najmniej 2 miesiące. Sprawdź, czy są
              zapłacone, albo oznacz je jako gotówka.
            </Text>
            <Group gap="xs">
              {overview.to_explain.map((item) => (
                <Button key={item.month} size="xs" variant="light" color="red"
                  onClick={() => go('statements', item.month)}>
                  {item.label}: {item.count}
                </Button>
              ))}
            </Group>
          </Stack>
        </Alert>
      ) : null}

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        {overview === null ? (
          <>
            <CardSkeleton />
            <CardSkeleton />
          </>
        ) : (
          <>
            <StepCard
              icon={<IconFileInvoice size={26} />}
              title={`Faktury: ${monthLabel}`}
              done={overview.invoices.count > 0}
              lines={
                overview.invoices.count
                  ? [
                      `${overview.invoices.downloaded} z ${overview.invoices.count} faktur zapisanych jako PDF`,
                      `Pobrano z KSeF ${formatDateTime(overview.invoices.fetched_at)}`,
                    ]
                  : ['Faktury z tego miesiąca nie zostały jeszcze pobrane.']
              }
              action={overview.invoices.count ? 'Pokaż faktury' : 'Pobierz faktury'}
              onClick={() => go('invoices', month)}
            />
            <StepCard
              icon={<IconBuildingBank size={26} />}
              title={`Wyciągi i płatności: ${monthLabel}`}
              done={overview.reconcile !== null && overview.reconcile.missing === 0 && overview.reconcile.unpaid === 0}
              warning={overview.reconcile !== null && (overview.reconcile.missing > 0 || overview.reconcile.unpaid > 0)}
              lines={
                overview.reconcile
                  ? [
                      `Obciążenia z fakturą: ${overview.reconcile.matched}, bez faktury: ${overview.reconcile.missing}`,
                      `Faktury: zapłacone ${overview.payments.paid}, gotówka ${overview.payments.cash}, ` +
                        `niezapłacone ${overview.reconcile.unpaid}`,
                      `Porównano ${formatDateTime(overview.reconcile.created_at)}`,
                    ]
                  : [
                      overview.statements
                        ? `Wyciągów w folderze: ${overview.statements}. Porównanie nie zostało jeszcze wykonane.`
                        : 'Brak wyciągów za ten miesiąc.',
                    ]
              }
              action={overview.reconcile ? 'Pokaż wynik' : 'Przejdź do wyciągów'}
              onClick={() => go('statements', month)}
            />
          </>
        )}
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" mt="lg">
        <Card withBorder padding="lg">
          <Group gap="sm" mb="md">
            <ThemeIcon variant="light">
              <IconHistory size={18} />
            </ThemeIcon>
            <Text fw={600}>Ostatnie operacje</Text>
          </Group>
          {history === null ? (
            <CardSkeleton />
          ) : history.length === 0 ? (
            <Text size="sm" c="dimmed">
              Jeszcze nic nie zrobiono. Zacznij od pobrania faktur.
            </Text>
          ) : (
            <Timeline bulletSize={22} lineWidth={2}>
              {history.map((item) => (
                <Timeline.Item
                  key={item.at + item.kind}
                  bullet={item.kind === 'download' ? <IconCloudDownload size={12} /> : <IconScale size={12} />}
                  color={item.ok ? 'ksef' : 'red'}
                  title={
                    <Group gap={6}>
                      <Text size="sm" fw={500}>
                        {HISTORY_LABELS[item.kind]} · {dayjs(`${item.month}-01`).format('MMMM YYYY')}
                      </Text>
                      {item.ok ? null : (
                        <Badge size="xs" color="red" variant="light">
                          błąd
                        </Badge>
                      )}
                    </Group>
                  }
                >
                  <Text size="xs" c="dimmed">
                    {formatDateTime(item.at)} · {item.summary}
                  </Text>
                </Timeline.Item>
              ))}
            </Timeline>
          )}
        </Card>

        <Stack gap="lg">
          <Card withBorder padding="lg">
            <Group gap="sm" mb="sm">
              <ThemeIcon variant="light" color={certColor}>
                <IconCertificate size={18} />
              </ThemeIcon>
              <Text fw={600}>Certyfikat KSeF</Text>
              <Badge color={certColor} variant="light" ml="auto">
                {cert.days_left > 0 ? `ważny jeszcze ${cert.days_left} dni` : 'wygasł'}
              </Badge>
            </Group>
            <Text size="sm">{cert.name}</Text>
            <Text size="sm" c="dimmed">
              Ważny do {formatDate(cert.valid_to)}
            </Text>
          </Card>
          <Card withBorder padding="lg">
            <Text fw={600} mb="sm">
              Foldery
            </Text>
            <Stack gap={6}>
              <PathLabel path={status.invoices_dir!} parts={3} />
              <PathLabel path={status.statements_dir!} parts={3} />
            </Stack>
          </Card>
        </Stack>
      </SimpleGrid>
    </>
  )
}

function greeting() {
  const hour = new Date().getHours()
  return hour < 18 ? 'Dzień dobry!' : 'Dobry wieczór!'
}

function StepCard(props: {
  icon: React.ReactNode
  title: string
  lines: string[]
  action: string
  onClick: () => void
  done?: boolean
  warning?: boolean
}) {
  const statusBadge = props.warning ? (
    <Badge color="red" variant="light" leftSection={<IconCircleX size={12} />}>
      do wyjaśnienia
    </Badge>
  ) : props.done ? (
    <Badge color="green" variant="light" leftSection={<IconCircleCheck size={12} />}>
      gotowe
    </Badge>
  ) : (
    <Badge color="gray" variant="light">
      do zrobienia
    </Badge>
  )
  return (
    <Card withBorder padding="xl">
      <Group align="flex-start" wrap="nowrap">
        <ThemeIcon size={52} radius="md" variant="light">
          {props.icon}
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group justify="space-between" gap="xs">
            <Title order={4} tt="none">
              {props.title}
            </Title>
            {statusBadge}
          </Group>
          {props.lines.map((line) => (
            <Text key={line} c="dimmed" size="sm">
              {line}
            </Text>
          ))}
          <Group mt="xs">
            <Button rightSection={<IconArrowRight size={16} />} onClick={props.onClick}>
              {props.action}
            </Button>
          </Group>
        </Stack>
      </Group>
    </Card>
  )
}
