import { Alert, Button, Center, Stack } from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Błąd w interfejsie pokazuje komunikat zamiast pustego okna. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Błąd interfejsu', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <Center h="100%" p="xl">
        <Alert color="red" icon={<IconAlertTriangle />} title="Coś poszło nie tak" maw={560}>
          <Stack>
            Ten ekran nie mógł się wyświetlić. Twoje dane są bezpieczne.
            <Button variant="light" color="red" onClick={() => window.location.reload()}>
              Odśwież aplikację
            </Button>
          </Stack>
        </Alert>
      </Center>
    )
  }
}
