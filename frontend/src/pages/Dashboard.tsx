import { Alert, Badge, Button, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core'
import {
  IconAlertTriangle,
  IconArrowRight,
  IconBuildingBank,
  IconCertificate,
  IconFileInvoice,
  IconFolder,
} from '@tabler/icons-react'
import dayjs from 'dayjs'
import type { Page } from '../App'
import type { Status } from '../api'
import { formatDate } from '../format'
import { PageHeader } from './PageHeader'

interface Props {
  status: Status
  go: (page: Page, month?: string) => void
}

export function Dashboard({ status, go }: Props) {
  const previousLabel = dayjs(`${status.previous_month}-01`).format('MMMM YYYY')

  if (!status.configured) {
    return (
      <>
        <PageHeader title="Pulpit" />
        <Alert color="orange" icon={<IconAlertTriangle />} title="Aplikacja nie jest jeszcze skonfigurowana">
          {status.error}
          <Button mt="md" onClick={() => go('settings')}>
            Przejdź do ustawień
          </Button>
        </Alert>
      </>
    )
  }

  const cert = status.certificate!
  const certColor = cert.days_left < 30 ? 'red' : cert.days_left < 90 ? 'orange' : 'green'

  return (
    <>
      <PageHeader title="Pulpit" subtitle={`Dzień dobry! Do rozliczenia jest zwykle ${previousLabel}.`} />

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <ActionCard
          icon={<IconFileInvoice size={26} />}
          title="Faktury zakupowe"
          text={`Pobierz z KSeF faktury za ${previousLabel} i zapisz je jako PDF.`}
          action="Przejdź do faktur"
          onClick={() => go('invoices', status.previous_month)}
        />
        <ActionCard
          icon={<IconBuildingBank size={26} />}
          title="Wyciągi i płatności"
          text={`Wrzuć wyciągi bankowe za ${previousLabel} i sprawdź, które faktury są zapłacone.`}
          action="Przejdź do wyciągów"
          onClick={() => go('statements', status.previous_month)}
        />
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" mt="lg">
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
          <Group gap="sm" mb="sm">
            <ThemeIcon variant="light">
              <IconFolder size={18} />
            </ThemeIcon>
            <Text fw={600}>Foldery</Text>
          </Group>
          <Stack gap={6}>
            <FolderLine label="Faktury" path={status.invoices_dir!} />
            <FolderLine label="Wyciągi" path={status.statements_dir!} />
          </Stack>
        </Card>
      </SimpleGrid>
    </>
  )
}

function ActionCard(props: { icon: React.ReactNode; title: string; text: string; action: string; onClick: () => void }) {
  return (
    <Card withBorder padding="xl">
      <Group align="flex-start" wrap="nowrap">
        <ThemeIcon size={52} radius="md" variant="light">
          {props.icon}
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1 }}>
          <Title order={4}>{props.title}</Title>
          <Text c="dimmed" size="sm">
            {props.text}
          </Text>
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

function FolderLine({ label, path }: { label: string; path: string }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="sm" style={{ wordBreak: 'break-all' }}>
        {path}
      </Text>
    </div>
  )
}
