import '@mantine/core/styles.css'
import '@mantine/dates/styles.css'
import '@mantine/dropzone/styles.css'
import '@mantine/notifications/styles.css'
import './index.css'

import { MantineProvider, createTheme } from '@mantine/core'
import { DatesProvider } from '@mantine/dates'
import { Notifications } from '@mantine/notifications'
import dayjs from 'dayjs'
import 'dayjs/locale/pl'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'

dayjs.locale('pl')

const theme = createTheme({
  primaryColor: 'ksef',
  colors: {
    ksef: [
      '#e8f1fa', '#d0e1f2', '#a3c3e6', '#72a3d9', '#4a88ce',
      '#3077c8', '#1c5d99', '#174f83', '#12416c', '#0c2f4f',
    ],
  },
  primaryShade: 6,
  defaultRadius: 'md',
  fontFamily: 'Segoe UI, -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif',
  headings: { fontWeight: '650' },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="light">
      <DatesProvider settings={{ locale: 'pl', firstDayOfWeek: 1 }}>
        <Notifications position="top-right" />
        <App />
      </DatesProvider>
    </MantineProvider>
  </StrictMode>,
)
