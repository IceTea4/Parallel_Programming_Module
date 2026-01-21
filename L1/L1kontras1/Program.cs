namespace L1kontras1
{
    class Program
    {
        static void Main(string[] args)
        {
            var resultMonitor = new resultMonitor();
            var threads = new List<Thread>();

            for (int nr = 1; nr <= 5; nr++)
            {
                int id = nr;

                var t = new Thread(() =>
                {
                    if (id <= 2)
                    {
                        while (!resultMonitor.IsDone())
                        {
                            resultMonitor.ChangeBy(id);

                            Thread.Yield();
                        }
                    }
                    else
                    {
                        int lastVer = -1;

                        while (true)
                        {
                            var (c, d, ver) = resultMonitor.ReadNext(ref lastVer);
                            Console.WriteLine($"[P{id}] c={c}, d={d} (ver={ver})");

                            if (resultMonitor.IsDone() && ver == resultMonitor.GetVersion().ver)
                            {
                                break;
                            }
                        }
                    }
                });

                t.Start();
                threads.Add(t);
            }

            foreach(var t in threads)
            {
                t.Join();
            }

            var (c, d, ver) = resultMonitor.GetVersion();
            Console.WriteLine($"c = {c}, d = {d}");
        }
    }
}
