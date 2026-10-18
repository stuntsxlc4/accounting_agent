import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  ThemeIcon,
} from '@mantine/core'
import { Dropzone, PDF_MIME_TYPE } from '@mantine/dropzone'
import { notifications } from '@mantine/notifications'
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconFileSpreadsheet,
  IconFileTypePdf,
  IconFolderOpen,
  IconScale,
  IconUpload,
} from '@tabler/icons-react'
import { useCallback, useEffect, useState } from 'react'
import { api, type DebitRow, type Job, type MonthStatements, type ReconcileResult, type UnpaidRow } from '../api'
import { JobProgress } from '../components/JobProgress'
import { MonthSelect } from '../components/MonthSelect'
import { formatDate, formatMoney } from '../format'
import { PageHeader } from './PageHeader'

interface Props {
  month: string
  onMonthChange: (month: string) => void
}

const UNPAID_COLORS: Record<string, string> = {
  'brak płatności': 'red',
  'zapłacona kartą spoza wyciągów': 'yellow',
  'zapłacona wg faktury': 'green',
  'skorygowana do zera': 'gray',
  korekta: 'gray',
}

export function Statements({ month, onMonthChange }: Props) {
  const [data, setData] = useState<MonthStatements | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [result, setResult] = useState<ReconcileResult | null>(null)
  const [uploading, setUploading] = useState(false)

  const load = useCallback(() => api.statements(month).then(setData), [month])

  useEffect(() => {
    setData(null)
    setResult(null)
    load()
  }, [load])

  const upload = async (files: File[]) => {
    setUploading(true)
    try {
      setData(await api.upload(month, files))
      notifications.show({ color: 'green', message: `Dodano wyciągów: ${files.length}` })
    } catch (e) {
      notifications.show({ color: 'red', title: 'Nie dodano plików', message: String(e) })
    } finally {
      setUploading(false)
    }
  }

  const start = async () => {
    try {
      setResult(null)
      setJobId((await api.reconcile(month)).job_id)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Nie można rozpocząć', message: String(e) })
    }
  }

  const finished = useCallback(
    (job: Job<ReconcileResult>) => {
      if (job.status === 'done') {
        setResult(job.result)
        setJobId(null)
      }
      load()
    },
    [load],
  )

  const open = (target: 'statements_folder' | 'report', name?: string) =>
    api.open(target, month, name).catch((e) => notifications.show({ color: 'red', message: String(e) }))

  const running = jobId !== null
  const files = data?.files ?? []

  return (
    <>
      <PageHeader title="Wyciągi i płatności" subtitle={data ? `${data.label} · ${data.folder}` : undefined}>
        <MonthSelect month={month} onChange={onMonthChange} disabled={running} />
        <Button leftSection={<IconScale size={18} />} onClick={start} loading={running} disabled={!files.length}>
          Porównaj z fakturami
        </Button>
        <Button variant="default" leftSection={<IconFolderOpen size={18} />} onClick={() => open('statements_folder')}>
          Otwórz folder
        </Button>
      </PageHeader>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Dropzone onDrop={upload} accept={PDF_MIME_TYPE} loading={uploading} disabled={running}>
          <Group justify="center" gap="lg" mih={140} style={{ pointerEvents: 'none' }}>
            <ThemeIcon size={56} radius="xl" variant="light">
              <IconUpload size={28} />
            </ThemeIcon>
            <div>
              <Text fw={600}>Przeciągnij tutaj wyciągi PDF</Text>
              <Text size="sm" c="dimmed">
                albo kliknij, aby wybrać pliki. Alior, Erste, UniCredit.
              </Text>
            </div>
          </Group>
        </Dropzone>

        <Card withBorder>
          <Group justify="space-between" mb="xs">
            <Text fw={600}>Wyciągi w folderze miesiąca</Text>
            <Badge variant="light">{files.length}</Badge>
          </Group>
          {files.length === 0 ? (
            <Text size="sm" c="dimmed">
              Brak wyciągów. Dodaj pliki PDF obok.
            </Text>
          ) : (
            <List spacing={4} size="sm" icon={<IconFileTypePdf size={16} color="var(--mantine-color-red-6)" />}
              style={{ maxHeight: 150, overflowY: 'auto' }}>
              {files.map((f) => (
                <List.Item key={f.name}>{f.name}</List.Item>
              ))}
            </List>
          )}
          {data?.report ? (
            <Button mt="sm" size="xs" variant="light" color="green"
              leftSection={<IconFileSpreadsheet size={16} />} onClick={() => open('report', data.report!)}>
              Otwórz ostatnie zestawienie Excel
            </Button>
          ) : null}
        </Card>
      </SimpleGrid>

      {jobId ? (
        <Stack mt="lg">
          <JobProgress jobId={jobId} onFinished={finished} />
        </Stack>
      ) : null}

      {result ? <Results result={result} onOpenReport={() => open('report', result.report)} /> : null}
    </>
  )
}

function Results({ result, onOpenReport }: { result: ReconcileResult; onOpenReport: () => void }) {
  const matched = result.banks.reduce((n, b) => n + b.matched.length, 0)
  const missing = result.banks.reduce((n, b) => n + b.missing.length, 0)
  const unpaidOpen = result.unpaid.filter((u) => u.status === 'brak płatności').length

  return (
    <Stack mt="lg" gap="lg">
      <Group justify="space-between">
        <Text fw={600} size="lg">
          Wynik porównania
        </Text>
        <Button color="green" leftSection={<IconFileSpreadsheet size={18} />} onClick={onOpenReport}>
          Otwórz zestawienie Excel
        </Button>
      </Group>

      {result.unreadable.length ? (
        <Alert color="orange" icon={<IconAlertTriangle />} title="Nie wszystkie wyciągi udało się odczytać">
          {result.unreadable.map((m) => (
            <Text key={m} size="sm">
              {m}
            </Text>
          ))}
        </Alert>
      ) : null}

      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Odczytane wyciągi" value={result.statements} />
        <Stat label="Obciążenia z fakturą" value={matched} color="green" />
        <Stat label="Obciążenia BEZ FAKTURY" value={missing} color={missing ? 'red' : 'green'} />
        <Stat label="Faktury bez płatności" value={unpaidOpen} color={unpaidOpen ? 'red' : 'green'}
          hint={`z ${result.unpaid.length} spoza wyciągów`} />
      </SimpleGrid>

      <Card withBorder padding="md">
        <Tabs defaultValue={result.banks[0]?.name ?? 'unpaid'}>
          <Tabs.List>
            {result.banks.map((bank) => (
              <Tabs.Tab key={bank.name} value={bank.name}
                rightSection={bank.missing.length ? <Badge color="red" size="sm" circle>{bank.missing.length}</Badge> : null}>
                {bank.name}
              </Tabs.Tab>
            ))}
            <Tabs.Tab value="unpaid">Faktury bez płatności</Tabs.Tab>
          </Tabs.List>

          {result.banks.map((bank) => (
            <Tabs.Panel key={bank.name} value={bank.name} pt="md">
              <Stack gap="lg">
                <DebitTable title="Obciążenia z fakturą" rows={bank.matched} color="green" />
                <DebitTable title="Obciążenia BEZ FAKTURY – do wyjaśnienia" rows={bank.missing} color="red" />
                <Accordion variant="contained">
                  <Accordion.Item value="other">
                    <Accordion.Control>
                      Bez faktury z natury: opłaty, lokaty, podatki, ZUS, wynagrodzenia, przelewy własne (
                      {bank.other.length})
                    </Accordion.Control>
                    <Accordion.Panel>
                      <DebitTable rows={bank.other} color="gray" />
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              </Stack>
            </Tabs.Panel>
          ))}

          <Tabs.Panel value="unpaid" pt="md">
            <UnpaidTable rows={result.unpaid} />
          </Tabs.Panel>
        </Tabs>
      </Card>
    </Stack>
  )
}

function Stat({ label, value, color, hint }: { label: string; value: number; color?: string; hint?: string }) {
  return (
    <Card withBorder>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fz={30} fw={700} c={color}>
        {value}
      </Text>
      {hint ? (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      ) : null}
    </Card>
  )
}

function DebitTable({ title, rows, color }: { title?: string; rows: DebitRow[]; color: string }) {
  const icon = color === 'green' ? <IconCircleCheck size={18} /> : color === 'red' ? <IconCircleX size={18} /> : null
  return (
    <Stack gap="xs">
      {title ? (
        <Group gap="xs">
          {icon ? (
            <ThemeIcon size="sm" variant="light" color={color}>
              {icon}
            </ThemeIcon>
          ) : null}
          <Text fw={600}>
            {title}: {rows.length}
          </Text>
        </Group>
      ) : null}
      {rows.length === 0 ? (
        <Text size="sm" c="dimmed">
          Brak.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped verticalSpacing="xs" fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Data obciążenia</Table.Th>
                <Table.Th ta="right">Kwota</Table.Th>
                <Table.Th>Rodzaj</Table.Th>
                <Table.Th>Kontrahent / opis</Table.Th>
                <Table.Th>Faktura</Table.Th>
                <Table.Th>Uwagi</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row, i) => (
                <Table.Tr key={i}>
                  <Table.Td>
                    {formatDate(row.booking_date)}
                    {row.operation_date && row.operation_date !== row.booking_date ? (
                      <Text size="xs" c="dimmed">
                        operacja {formatDate(row.operation_date)}
                      </Text>
                    ) : null}
                  </Table.Td>
                  <Table.Td ta="right" className="amount">
                    {formatMoney(row.amount, row.currency)}
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={row.kind === 'karta' ? 'grape' : row.kind === 'przelew' ? 'blue' : 'gray'}>
                      {row.kind}
                    </Badge>
                  </Table.Td>
                  <Table.Td maw={380}>
                    <Text size="sm" lineClamp={2}>
                      {row.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {row.invoice ? (
                      <>
                        <Text size="sm" fw={500}>
                          {row.invoice.number}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {formatDate(row.invoice.issue_date)} · {row.invoice.seller}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {row.method}
                        </Text>
                      </>
                    ) : color === 'red' ? (
                      <Badge color="red">BRAK FAKTURY</Badge>
                    ) : null}
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{row.note}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  )
}

function UnpaidTable({ rows }: { rows: UnpaidRow[] }) {
  if (rows.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Wszystkie faktury z miesiąca znaleziono na wyciągach.
      </Text>
    )
  }
  return (
    <Table striped verticalSpacing="xs" fz="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Data faktury</Table.Th>
          <Table.Th>Numer</Table.Th>
          <Table.Th>Sprzedawca</Table.Th>
          <Table.Th ta="right">Brutto</Table.Th>
          <Table.Th>Status</Table.Th>
          <Table.Th>Płatność według faktury / uwagi</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map((row) => (
          <Table.Tr key={`${row.number}-${row.issue_date}`}>
            <Table.Td>{formatDate(row.issue_date)}</Table.Td>
            <Table.Td>{row.number}</Table.Td>
            <Table.Td>{row.seller}</Table.Td>
            <Table.Td ta="right" className="amount">
              {formatMoney(row.gross, row.currency)}
            </Table.Td>
            <Table.Td>
              <Badge variant="light" color={UNPAID_COLORS[row.status] ?? 'gray'}>
                {row.status}
              </Badge>
            </Table.Td>
            <Table.Td>{row.details}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
