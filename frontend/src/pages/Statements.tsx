import {
  Accordion,
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  ThemeIcon,
  Tooltip,
} from '@mantine/core'
import { Dropzone, PDF_MIME_TYPE } from '@mantine/dropzone'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconFileSpreadsheet,
  IconFileTypePdf,
  IconFolderOpen,
  IconScale,
  IconTrash,
  IconUpload,
} from '@tabler/icons-react'
import dayjs from 'dayjs'
import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  api,
  errorMessage,
  type DebitRow,
  type Job,
  type MonthPayments,
  type MonthStatements,
  type ReconcileRecord,
  type UploadResult,
} from '../api'
import { JobError, JobProgress } from '../components/JobProgress'
import { CardSkeleton } from '../components/Loading'
import { MonthSelect } from '../components/MonthSelect'
import { PaymentsTable } from '../components/Payments'
import { PathLabel } from '../components/PathLabel'
import { formatDate, formatDateTime, formatMoney, formatSize } from '../format'
import { useJob } from '../useJob'
import { PageHeader } from './PageHeader'

interface Props {
  month: string
  onMonthChange: (month: string) => void
}

export function Statements({ month, onMonthChange }: Props) {
  const [data, setData] = useState<MonthStatements | null>(null)
  const [record, setRecord] = useState<ReconcileRecord | null>(null)
  const [payments, setPayments] = useState<MonthPayments | null>(null)
  const [uploading, setUploading] = useState(false)

  const load = useCallback(() => {
    api
      .statements(month)
      .then(setData)
      .catch((e) => notifications.show({ color: 'red', message: errorMessage(e) }))
    api
      .lastReconcile(month)
      .then((r) => setRecord(r.record))
      .catch(() => setRecord(null))
    api
      .payments(month)
      .then(setPayments)
      .catch(() => setPayments(null))
  }, [month])

  const onDone = useCallback(
    (job: Job<ReconcileRecord>) => {
      if (job.status === 'done' && job.result) {
        setRecord(job.result)
        notifications.show({ color: 'green', title: 'Porównanie gotowe', message: 'Zestawienie Excel zapisano w folderze wyciągów.' })
      }
      load()
    },
    [load],
  )
  const job = useJob('reconcile', onDone)

  useEffect(() => {
    load()
  }, [load])

  const send = async (files: File[], overwrite = false) => {
    setUploading(true)
    try {
      const result = await api.upload(month, files, overwrite)
      setData(result)
      notifications.show({ color: 'green', title: 'Wyciągi dodane', message: uploadSummary(result) })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        confirmReplace((e.body as { conflicts: string[] }).conflicts, () => send(files, true))
      } else {
        notifications.show({ color: 'red', title: 'Nie dodano plików', message: errorMessage(e) })
      }
    } finally {
      setUploading(false)
    }
  }

  const remove = (name: string) =>
    modals.openConfirmModal({
      title: 'Usunąć wyciąg?',
      children: (
        <Text size="sm">
          Plik <b>{name}</b> zostanie przeniesiony do kosza. Możesz go stamtąd przywrócić.
        </Text>
      ),
      labels: { confirm: 'Przenieś do kosza', cancel: 'Anuluj' },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        api
          .removeStatement(month, name)
          .then(setData)
          .catch((e) => notifications.show({ color: 'red', message: errorMessage(e) })),
    })

  const open = (target: 'statements_folder' | 'report', name?: string) =>
    api.open(target, month, name).catch((e) => notifications.show({ color: 'red', message: errorMessage(e) }))

  const files = data?.files ?? []

  return (
    <>
      <PageHeader
        title="Wyciągi i płatności"
        subtitle={data ? <PathLabel path={data.folder} onOpen={() => open('statements_folder')} /> : null}
      >
        <MonthSelect month={month} onChange={onMonthChange} disabled={job.running} />
        <Button
          leftSection={<IconScale size={18} />}
          onClick={() => job.start(() => api.reconcile(month))}
          loading={job.running}
          disabled={!files.length}
        >
          Porównaj z fakturami
        </Button>
        <Button variant="default" leftSection={<IconFolderOpen size={18} />} onClick={() => open('statements_folder')}>
          Otwórz folder
        </Button>
      </PageHeader>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Dropzone onDrop={(f) => send(f)} accept={PDF_MIME_TYPE} loading={uploading} disabled={job.running}
          onReject={() => notifications.show({ color: 'orange', message: 'Można dodawać tylko pliki PDF.' })}>
          <Stack align="center" justify="center" gap={6} mih={150} style={{ pointerEvents: 'none' }}>
            <ThemeIcon size={52} radius="xl" variant="light">
              <IconUpload size={26} />
            </ThemeIcon>
            <Text fw={600} mt={4}>
              Przeciągnij tutaj wyciągi PDF
            </Text>
            <Text size="sm" c="dimmed" ta="center">
              albo kliknij, aby wybrać pliki. Obsługiwane banki: Alior, Erste, UniCredit.
            </Text>
          </Stack>
        </Dropzone>

        {data === null ? (
          <CardSkeleton />
        ) : (
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
              <ScrollArea.Autosize mah={170}>
                <Stack gap={2}>
                  {files.map((f) => (
                    <Group key={f.name} gap="xs" wrap="nowrap" justify="space-between">
                      <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                        <IconFileTypePdf size={16} color="var(--mantine-color-red-6)" style={{ flexShrink: 0 }} />
                        <Text size="sm" truncate>
                          {f.name}
                        </Text>
                      </Group>
                      <Group gap="xs" wrap="nowrap">
                        <Text size="xs" c="dimmed">
                          {formatSize(f.size)}
                        </Text>
                        <Tooltip label="Przenieś do kosza" withArrow>
                          <ActionIcon variant="subtle" color="gray" size="sm" onClick={() => remove(f.name)}
                            aria-label={`Usuń ${f.name}`} disabled={job.running}>
                            <IconTrash size={15} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    </Group>
                  ))}
                </Stack>
              </ScrollArea.Autosize>
            )}
          </Card>
        )}
      </SimpleGrid>

      <Stack mt="lg">
        <JobError error={job.error} onClose={job.clearError} />
        {job.jobId ? <JobProgress jobId={job.jobId} onFinished={job.finished} /> : null}
      </Stack>

      {record && !job.running ? (
        <Results
          record={record}
          payments={payments}
          onPaymentsChanged={setPayments}
          onOpenReport={() => open('report', record.result.report)}
        />
      ) : null}
    </>
  )
}

function uploadSummary(result: UploadResult) {
  const parts = [
    result.added.length && `nowe: ${result.added.length}`,
    result.replaced.length && `zastąpione: ${result.replaced.length}`,
    result.skipped.length && `już były: ${result.skipped.length}`,
  ].filter(Boolean)
  return parts.join(', ') || 'Brak zmian'
}

function confirmReplace(conflicts: string[], onConfirm: () => void) {
  modals.openConfirmModal({
    title: 'Zastąpić istniejące pliki?',
    children: (
      <Stack gap="xs">
        <Text size="sm">W folderze są już pliki o tych nazwach, ale z inną zawartością:</Text>
        {conflicts.map((name) => (
          <Text key={name} size="sm" fw={500}>
            {name}
          </Text>
        ))}
      </Stack>
    ),
    labels: { confirm: 'Zastąp', cancel: 'Anuluj' },
    confirmProps: { color: 'orange' },
    onConfirm,
  })
}

function Results({
  record,
  payments,
  onPaymentsChanged,
  onOpenReport,
}: {
  record: ReconcileRecord
  payments: MonthPayments | null
  onPaymentsChanged: (data: MonthPayments) => void
  onOpenReport: () => void
}) {
  const result = record.result
  const matched = result.banks.reduce((n, b) => n + b.matched.length, 0)
  const missing = result.banks.reduce((n, b) => n + b.missing.length, 0)
  const invoices = payments?.invoices ?? []
  const unpaid = invoices.filter((i) => ['niezapłacona', 'do wyjaśnienia', 'sprzeczność'].includes(i.status)).length

  return (
    <Stack mt="lg" gap="lg">
      <Group justify="space-between">
        <div>
          <Text fw={600} size="lg">
            Wynik porównania
          </Text>
          <Text size="sm" c="dimmed">
            z {formatDateTime(record.created_at)}, faktur z KSeF: {result.invoice_count}
          </Text>
        </div>
        <Button color="green" leftSection={<IconFileSpreadsheet size={18} />} onClick={onOpenReport}>
          Otwórz zestawienie Excel
        </Button>
      </Group>

      {record.updated_months?.length ? (
        <Alert color="blue" icon={<IconCircleCheck />} title="Zaktualizowano wcześniejsze miesiące">
          Płatności z tych wyciągów opłaciły faktury z:{' '}
          {record.updated_months.map((m) => dayjs(`${m}-01`).format('MMMM YYYY')).join(', ')}. Ich zestawienia
          Excel zostały przeliczone.
        </Alert>
      ) : null}

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
        <Stat label="Faktury niezapłacone" value={unpaid} color={unpaid ? 'red' : 'green'}
          hint={`z ${invoices.length} faktur miesiąca`} />
      </SimpleGrid>

      <Card withBorder padding="md">
        <Tabs defaultValue={result.banks[0]?.name ?? 'invoices'}>
          <Tabs.List>
            {result.banks.map((bank) => (
              <Tabs.Tab key={bank.name} value={bank.name}
                rightSection={bank.missing.length ? <Badge color="red" size="sm" circle>{bank.missing.length}</Badge> : null}>
                {bank.name}
              </Tabs.Tab>
            ))}
            <Tabs.Tab value="invoices"
              rightSection={unpaid ? <Badge color="red" size="sm" circle>{unpaid}</Badge> : null}>
              Faktury miesiąca: płatności
            </Tabs.Tab>
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

          <Tabs.Panel value="invoices" pt="md">
            {payments ? <PaymentsTable data={payments} onChanged={onPaymentsChanged} /> : null}
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
                <Table.Th className="nowrap">Data obciążenia</Table.Th>
                <Table.Th ta="right">Kwota</Table.Th>
                <Table.Th w={130}>Rodzaj</Table.Th>
                <Table.Th>Kontrahent / opis</Table.Th>
                <Table.Th miw={200}>Faktura</Table.Th>
                <Table.Th miw={180}>Uwagi</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row, i) => (
                <Table.Tr key={i}>
                  <Table.Td className="nowrap">
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
                    <Badge variant="light" style={{ overflow: 'visible' }}
                      color={row.kind === 'karta' ? 'grape' : row.kind === 'przelew' ? 'blue' : 'gray'}>
                      {row.kind}
                    </Badge>
                  </Table.Td>
                  <Table.Td maw={420}>
                    {row.counterparty ? (
                      <Text size="sm" fw={500} lineClamp={2}>
                        {row.counterparty}
                      </Text>
                    ) : null}
                    <Tooltip label={row.description} multiline maw={520} openDelay={400} withArrow>
                      <Text size="xs" c="dimmed" lineClamp={2}>
                        {transferTitle(row.description)}
                      </Text>
                    </Tooltip>
                    {row.account ? (
                      <Text size="xs" c="dimmed" ff="monospace">
                        {row.account}
                      </Text>
                    ) : null}
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
                      <Badge color="red" style={{ overflow: 'visible' }}>
                        BRAK FAKTURY
                      </Badge>
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

/** Tytuł przelewu z opisu operacji, a gdy go brak, sam opis. */
function transferTitle(description: string) {
  const title = description.match(/Tytuł:\s*(.+?)(?:\s+Kwota VAT:|\s+Ident\.:|\s+FV:|$)/)
  return title ? `Tytuł: ${title[1]}` : description
}
