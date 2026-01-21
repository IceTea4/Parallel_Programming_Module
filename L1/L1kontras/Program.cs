using System.Threading;

namespace L1kontras
{
    class Program
    {
        static void Main(string[] args)
        {
            var resultMonitor = new ResultMonitor();

            char[] symbols = new char[] { 'A', 'B', 'C' };

            var threads = new List<Thread>();

            foreach (var sym in symbols)
            {
                char localSym = sym;

                var t = new Thread(() =>
                {
                    int myCount = 0;

                    while (!resultMonitor.IsDone())
                    {
                        if (resultMonitor.AddItem(localSym))
                        {
                            myCount++;

                            if (myCount >= 150)
                            {
                                resultMonitor.StopAll();
                                break;
                            }
                        }
                        else
                        {
                            Thread.Yield();
                        }
                    }
                });

                t.Start();
                threads.Add(t);
            }

            while (true)
            {
                Console.WriteLine(resultMonitor.GetItems());

                if (resultMonitor.IsDone())
                {
                    break;
                }
            }

                foreach (var t in threads)
            {
                t.Join();
            }

            Console.WriteLine("\nGalutinis rezultatas:");
            Console.WriteLine(resultMonitor.GetItems());
        }
    }
}
