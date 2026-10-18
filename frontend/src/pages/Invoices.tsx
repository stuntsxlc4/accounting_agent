import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Center,
  Group,
  SegmentedControl,
  Stack,
  Table,
  Text,
  TextInput,
  ThemeIcon,
  Tooltip,
  UnstyledButton,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconChevronDown,
  IconChevronUp,
  IconCloudDownload,
  IconFileTypePdf,
  IconFolderOpen,
  IconInbox,
  IconSearch,
  IconSelector,
} from '@tabler/icons-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, errorMessage, type InvoiceFile, type Job, type MonthInvoices } from '../api'
import { JobError, JobProgress } from '../components/JobProgress'
import { TableSkeleton } from '../components/Loading'
import { MonthSelect } from '../components/MonthSelect'
import { PathLabel } from '../components/PathLabel'
import { formatDate, formatDateTime, formatMoney, isCorrection } from '../format'
import { useJob } from '../useJob'
import { PageHeader } from './PageHeader'

interface Props {
  month: string
  onMonthChange: (month: string) => void
}

type SortKey = 'issue_date' | 'number' | 'seller' | 'gross'
type Filter = 'all' | 'invoices' | 'corrections' | 'missing'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'invoices', label: 'Faktury' },
  { value: 'corrections', label: 'Korekty' },
  { value: 'missing', label: 'Bez PDF' },
]

export function Invoices({ month, onMonthChange }: Props) {
  const [data, setData] = useState<MonthInvoices | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'issue_date', desc: false })

  const load = useCallback(
    () =>
      api
        .invoices(month)
        .then(setData)
        .catch((e) => notifications.show({ color: 'red', message: errorMessage(e) })),
    [month],
  )

  const onDone = useCallback(
    (job: Job<{ saved: number; count: number }>) => {
      if (job.status === 'done' && job.result) {
        notifications.show({
          color: 'green',
          title: 'Faktury pobrane',
          message: `W KSeF: ${job.result.count}, nowych plików: ${job.result.saved}`,
        })
      }
      load()
    },
    [load],
  )
  const job = useJob('download', onDone)

  useEffect(() => {
    load()
  }, [load])

  const open = (name?: string) =>
    api
      .open(name ? 'invoice' : 'invoices_folder', month, name)
      .catch((e) => notifications.show({ color: 'red', message: errorMessage(e) }))

  const all = useMemo(() => data?.invoices ?? [], [data])
  const visible = useMemo(() => filterAndSort(all, query, filter, sort), [all, query, filter, sort])
  const total = visible.filter((i) => !isCorrection(i.invoice_type)).reduce((sum, i) => sum + i.gross, 0)

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, desc: s.key === key ? !s.desc : key === 'gross' }))

  return (
    <>
      <PageHeader
        title="Faktury zakupowe"
        subtitle={
          data ? (
            <Group gap="md">
              <PathLabel path={data.folder} onOpen={() => open()} />
              {data.fetched_at ? (
                <Text size="sm" c="dimmed">
                  Ostatnie pobranie z KSeF: {formatDateTime(data.fetched_at)}
                </Text>
              ) : null}
            </Group>
          ) : null
        }
      >
        <MonthSelect month={month} onChange={onMonthChange} disabled={job.running} />
        <Button
          leftSection={<IconCloudDownload size={18} />}
          onClick={() => job.start(() => api.download(month))}
          loading={job.running}
        >
          Pobierz z KSeF
        </Button>
        <Button variant="default" leftSection={<IconFolderOpen size={18} />} onClick={() => open()}>
          Otwórz folder
        </Button>
      </PageHeader>

      <JobError error={job.error} onClose={job.clearError} />
      {job.jobId ? <JobProgress jobId={job.jobId} onFinished={job.finished} /> : null}

      {data === null ? (
        <TableSkeleton />
      ) : all.length === 0 ? (
        <EmptyState />
      ) : (
        <Card withBorder padding={0} mt="md">
          <Group p="md" justify="space-between" gap="sm">
            <TextInput
              placeholder="Szukaj: sprzedawca, numer, NIP"
              leftSection={<IconSearch size={16} />}
              value={query}
              onChange={(e) => setQuery(e.currentTarget.value)}
              w={320}
              aria-label="Szukaj faktur"
            />
            <SegmentedControl value={filter} onChange={(v) => setFilter(v as Filter)} data={FILTERS} />
          </Group>
          <Table.ScrollContainer minWidth={760}>
            <Table striped highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <SortHeader label="Data" field="issue_date" sort={sort} onSort={toggleSort} />
                  <SortHeader label="Numer" field="number" sort={sort} onSort={toggleSort} />
                  <SortHeader label="Sprzedawca" field="seller" sort={sort} onSort={toggleSort} />
                  <SortHeader label="Brutto" field="gross" sort={sort} onSort={toggleSort} right />
                  <Table.Th>Rodzaj</Table.Th>
                  <Table.Th ta="center">PDF</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {visible.map((invoice) => (
                  <InvoiceRow key={invoice.ksef_number} invoice={invoice} onOpen={open} />
                ))}
                {visible.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={6}>
                      <Text ta="center" c="dimmed" py="md">
                        Brak faktur spełniających kryteria.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ) : null}
              </Table.Tbody>
              <Table.Tfoot>
                <Table.Tr>
                  <Table.Th colSpan={3}>
                    Pokazano {visible.length} z {all.length}
                  </Table.Th>
                  <Table.Th ta="right" className="amount">
                    {formatMoney(total)}
                  </Table.Th>
                  <Table.Th colSpan={2}>
                    <Text size="xs" c="dimmed">
                      suma bez korekt
                    </Text>
                  </Table.Th>
                </Table.Tr>
              </Table.Tfoot>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
      <Text size="xs" c="dimmed" mt="xs">
        Pliki już pobrane nie są pobierane ponownie. KSeF pozwala pobrać do 64 faktur na godzinę.
      </Text>
    </>
  )
}

function filterAndSort(
  invoices: InvoiceFile[],
  query: string,
  filter: Filter,
  sort: { key: SortKey; desc: boolean },
) {
  const needle = query.trim().toLowerCase()
  const rows = invoices.filter((i) => {
    if (filter === 'invoices' && isCorrection(i.invoice_type)) return false
    if (filter === 'corrections' && !isCorrection(i.invoice_type)) return false
    if (filter === 'missing' && i.downloaded) return false
    return !needle || [i.seller, i.number, i.seller_nip].some((v) => v.toLowerCase().includes(needle))
  })
  const direction = sort.desc ? -1 : 1
  return rows.sort((a, b) => {
    const x = a[sort.key]
    const y = b[sort.key]
    const order = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'pl')
    return order * direction
  })
}

function SortHeader(props: {
  label: string
  field: SortKey
  sort: { key: SortKey; desc: boolean }
  onSort: (key: SortKey) => void
  right?: boolean
}) {
  const active = props.sort.key === props.field
  const Icon = active ? (props.sort.desc ? IconChevronDown : IconChevronUp) : IconSelector
  return (
    <Table.Th ta={props.right ? 'right' : undefined}>
      <UnstyledButton onClick={() => props.onSort(props.field)} aria-label={`Sortuj: ${props.label}`}>
        <Group gap={4} justify={props.right ? 'flex-end' : 'flex-start'} wrap="nowrap">
          <Text fw={600} size="sm">
            {props.label}
          </Text>
          <Icon size={14} stroke={1.8} opacity={active ? 1 : 0.4} />
        </Group>
      </UnstyledButton>
    </Table.Th>
  )
}

function InvoiceRow({ invoice, onOpen }: { invoice: InvoiceFile; onOpen: (name: string) => void }) {
  return (
    <Table.Tr>
      <Table.Td>{formatDate(invoice.issue_date)}</Table.Td>
      <Table.Td>{invoice.number}</Table.Td>
      <Table.Td>
        <Text size="sm">{invoice.seller}</Text>
        <Text size="xs" c="dimmed">
          NIP {invoice.seller_nip}
        </Text>
      </Table.Td>
      <Table.Td ta="right" className="amount">
        {formatMoney(invoice.gross, invoice.currency)}
      </Table.Td>
      <Table.Td>
        {isCorrection(invoice.invoice_type) ? (
          <Badge color="orange" variant="light">
            korekta
          </Badge>
        ) : (
          <Badge color="gray" variant="light">
            {invoice.invoice_type.toUpperCase()}
          </Badge>
        )}
      </Table.Td>
      <Table.Td ta="center">
        {invoice.downloaded ? (
          <Tooltip label={`Otwórz ${invoice.file_name}`} withArrow>
            <ActionIcon variant="light" color="red" onClick={() => onOpen(invoice.file_name)} aria-label="Otwórz PDF">
              <IconFileTypePdf size={18} />
            </ActionIcon>
          </Tooltip>
        ) : (
          <Text size="xs" c="dimmed">
            brak pliku
          </Text>
        )}
      </Table.Td>
    </Table.Tr>
  )
}

function EmptyState() {
  return (
    <Card withBorder mt="md">
      <Center p={48}>
        <Stack align="center" gap="xs">
          <ThemeIcon size={56} radius="xl" variant="light" color="gray">
            <IconInbox size={30} />
          </ThemeIcon>
          <Text fw={500}>Brak pobranych faktur za ten miesiąc</Text>
          <Text c="dimmed" size="sm">
            Kliknij „Pobierz z KSeF”, aby pobrać faktury i zapisać je jako PDF.
          </Text>
        </Stack>
      </Center>
    </Card>
  )
}
