using System.Text;

namespace L1kontras
{
    public class ResultMonitor
    {
        private readonly StringBuilder buffer = new StringBuilder("*");
        private readonly object m = new object();
        private int vowels = 0;
        private bool done = false;

        public bool IsDone()
        {
            lock (m)
            {
                return done;
            }
        }

        public void StopAll()
        {
            lock (m)
            {
                if (done)
                {
                    return;
                }

                done = true;
                Monitor.PulseAll(m);
            }
        }

        public bool AddItem(char symbol)
        {
            lock (m)
            {
                if (done)
                {
                    return false;
                }

                bool isVowel = (symbol == 'A');

                while (!isVowel && vowels < 3 && !done)
                {
                    Monitor.Wait(m);
                }

                if (done)
                {
                    return false;
                }

                buffer.Append(symbol);

                if (isVowel)
                {
                    vowels += 1;
                }
                else
                {
                    vowels -= 3;
                    if (vowels < 0)
                    {
                        vowels = 0;
                    }
                }

                Monitor.PulseAll(m);
                return true;
            }
        }

        public string GetItems()
        {
            lock (m)
            {
                return buffer.ToString();
            }
        }
    }
}
