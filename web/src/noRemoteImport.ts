// Stands in for @tscircuit/internal-dynamic-import, which loads modules from jscdn.tscircuit.com.
// Learn mode never fetches code from the network (DECISIONS L-2), so remote imports fail loudly.
export default async function noRemoteImport(specifier: string): Promise<never> {
  throw new Error(`reflow learn runs offline, so it doesn't load ${specifier} from the internet`)
}
