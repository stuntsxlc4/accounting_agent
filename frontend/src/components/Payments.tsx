import { Badge, Button, Group, SegmentedControl, Stack, Table, Text, Tooltip } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconArrowBackUp, IconCash } from '@tabler/icons-react'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { api, errorMessage, type MonthPayments, type PaymentRow, type PaymentStatus } from '../api'
import { formatDate, formatMoney } from '../format'

const STATUS_COLORS: Record<PaymentStatus, string> = {
  'zapłacona przelewem': 'green',
  'zapłacona kartą': 'green',
  gotówka: 'teal',
  niezapłacona: 'yellow',
  'do wyjaśnienia': 'red',
  sprzeczność: 'red',
  'skorygowana do zera': 'gray',
  korekta: 'gray',
}

const OPEN: PaymentStatus[] = ['niezapłacona', 'do wyjaśnienia', 'sprzeczność']
const PAID: PaymentStatus[] = ['zapłacona przelewem', 'zapłacona kartą', 'gotówka']

type Filter = 'all' | 'open' | 'paid'

/** Znaczek statusu płatności faktury. */
export function PaymentBadge({ row }: { row: PaymentRow }) {
  const later = row.paid_later && row.statement_month
  return (
    <Stack gap={2} align="flex-start">
      <Badge variant="light" color={STATUS_COLORS[row.status]} style={{ overflow: 'visible' }}>
        {row.status}
      </Badge>
      {later ? (
        <Text size="xs" c="dimmed">
          z wyciągu za {dayjs(`${row.statement_month}-01`).format('MMMM YYYY')}
        </Text>
      ) : null}
    </Stack>
  )
}

/** Przycisk „Oznacz jako gotówka” / „Cofnij”. */
export function CashAction({
  row,
  month,
  onChanged,
}: {
  row: PaymentRow
  month: string
  onChanged: (data: MonthPayments) => void
}) {
  const [busy, setBusy] = useState(false)
  const canMark = row.status === 'niezapłacona' || row.status === 'do wyjaśnienia'
  if (!canMark && !row.cash) return null

  const toggle = async () => {
    setBusy(true)
    try {
      onChanged(await api.setCash(month, row.ksef_number, !row.cash))
      notifications.show({
        color: 'green',
        message: row.cash
          ? `Cofnięto oznaczenie gotówki: ${row.number}`
          : `Oznaczono jako gotówka: ${row.number}`,
      })
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return row.cash ? (
    <Tooltip label="Cofnij oznaczenie gotówki" withArrow>
      <Button size="compact-xs" variant="subtle" color="gray" loading={busy} onClick={toggle}
        leftSection={<IconArrowBackUp size={14} />}>
        Cofnij
      </Button>
    </Tooltip>
  ) : (
    <Tooltip label="Zapłacona z własnych środków – do zwrotu z kasy firmy" withArrow multiline maw={260}>
      <Button size="compact-xs" variant="light" color="teal" loading={busy} onClick={toggle}
        leftSection={<IconCash size={14} />}>
        Gotówka
      </Button>
    </Tooltip>
  )
}

/** Faktury miesiąca ze statusem płatności. */
export function PaymentsTable({
  data,
  onChanged,
}: {
  data: MonthPayments
  onChanged: (data: MonthPayments) => void
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const rows = useMemo(
    () =>
      data.invoices.filter((row) =>
        filter === 'open' ? OPEN.includes(row.status) : filter === 'paid' ? PAID.includes(row.status) : true,
      ),
    [data, filter],
  )
  const open = data.invoices.filter((row) => OPEN.includes(row.status)).length

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Płatności z wyciągów kolejnych miesięcy aktualizują tę listę. „Gotówka” – zapłacone z własnych
          środków, oznaczane ręcznie.
        </Text>
        <SegmentedControl
          size="xs"
          value={filter}
          onChange={(v) => setFilter(v as Filter)}
          data={[
            { value: 'all', label: `Wszystkie (${data.invoices.length})` },
            { value: 'open', label: `Niezapłacone (${open})` },
            { value: 'paid', label: 'Zapłacone' },
          ]}
        />
      </Group>
      {rows.length === 0 ? (
        <Text size="sm" c="dimmed" py="md" ta="center">
          Brak faktur.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={1040}>
          <Table striped verticalSpacing="xs" fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th className="nowrap" w={110}>Data faktury</Table.Th>
                <Table.Th w={170}>Numer</Table.Th>
                <Table.Th>Sprzedawca</Table.Th>
                <Table.Th ta="right" w={120}>Brutto</Table.Th>
                <Table.Th w={190}>Płatność</Table.Th>
                <Table.Th miw={240}>Szczegóły</Table.Th>
                <Table.Th w={100} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => (
                <Table.Tr key={row.ksef_number}>
                  <Table.Td className="nowrap">{formatDate(row.issue_date)}</Table.Td>
                  <Table.Td>{row.number}</Table.Td>
                  <Table.Td>{row.seller}</Table.Td>
                  <Table.Td ta="right" className="amount">
                    {formatMoney(row.gross, row.currency)}
                  </Table.Td>
                  <Table.Td>
                    <PaymentBadge row={row} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{row.details}</Text>
                  </Table.Td>
                  <Table.Td>
                    <CashAction row={row} month={data.month} onChanged={onChanged} />
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
