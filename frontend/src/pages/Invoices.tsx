import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCloudDownload, IconFileTypePdf, IconFolderOpen, IconInbox } from '@tabler/icons-react'
import { useCallback, useEffect, useState } from 'react'
import { api, type Job, type MonthInvoices } from '../api'
import { JobProgress } from '../components/JobProgress'
import { MonthSelect } from '../components/MonthSelect'
import { formatDate, formatMoney, isCorrection } from '../format'
import { PageHeader } from './PageHeader'

interface Props {
  month: string
  onMonthChange: (month: string) => void
}

export function Invoices({ month, onMonthChange }: Props) {
  const [data, setData] = useState<MonthInvoices | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)

  const load = useCallback(() => api.invoices(month).then(setData), [month])

  useEffect(() => {
    setData(null)
    load()
  }, [load])

  const start = async () => {
    try {
      setJobId((await api.download(month)).job_id)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Nie można rozpocząć', message: String(e) })
    }
  }

  const finished = useCallback(
    (job: Job<{ saved: number; count: number }>) => {
      if (job.status === 'done' && job.result) {
        notifications.show({
          color: 'green',
          title: 'Faktury pobrane',
          message: `W KSeF: ${job.result.count}, nowych plików: ${job.result.saved}`,
        })
        setJobId(null)
      }
      load()
    },
    [load],
  )

  const open = (name?: string) =>
    api
      .open(name ? 'invoice' : 'invoices_folder', month, name)
      .catch((e) => notifications.show({ color: 'red', message: String(e) }))

  const invoices = data?.invoices ?? []
  const total = invoices.filter((i) => !isCorrection(i.invoice_type)).reduce((sum, i) => sum + i.gross, 0)
  const running = jobId !== null

  return (
    <>
      <PageHeader title="Faktury zakupowe" subtitle={data ? `${data.label} · ${data.folder}` : undefined}>
        <MonthSelect month={month} onChange={onMonthChange} disabled={running} />
        <Button leftSection={<IconCloudDownload size={18} />} onClick={start} loading={running}>
          Pobierz z KSeF
        </Button>
        <Button variant="default" leftSection={<IconFolderOpen size={18} />} onClick={() => open()}>
          Otwórz folder
        </Button>
      </PageHeader>

      {jobId ? <JobProgress jobId={jobId} onFinished={finished} /> : null}

      <Card withBorder padding={0} mt="md">
        {invoices.length === 0 ? (
          <Center p={60}>
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
        ) : (
          <Table striped highlightOnHover verticalSpacing="sm" horizontalSpacing="md">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Data</Table.Th>
                <Table.Th>Numer</Table.Th>
                <Table.Th>Sprzedawca</Table.Th>
                <Table.Th ta="right">Brutto</Table.Th>
                <Table.Th>Rodzaj</Table.Th>
                <Table.Th ta="center">PDF</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {invoices.map((invoice) => (
                <Table.Tr key={invoice.ksef_number}>
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
                      <Tooltip label={invoice.file_name}>
                        <ActionIcon variant="light" color="red" onClick={() => open(invoice.file_name)}>
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
              ))}
            </Table.Tbody>
            <Table.Tfoot>
              <Table.Tr>
                <Table.Th colSpan={3}>
                  Faktur: {invoices.length}
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
        )}
      </Card>
      <Group mt="xs">
        <Text size="xs" c="dimmed">
          Pliki już pobrane nie są pobierane ponownie. KSeF pozwala pobrać do 64 faktur na godzinę.
        </Text>
      </Group>
    </>
  )
}
