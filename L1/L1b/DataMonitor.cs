namespace L1b
{
	public class DataMonitor
	{
		private int count, tail, head;
		private bool completed;
        private readonly VolleyballPlayer[] buffer;
        private readonly object m = new object();

        public DataMonitor(int capacity)
        {
			if (capacity <= 0)
			{
				throw new ArgumentOutOfRangeException(nameof(capacity));
			}

            buffer = new VolleyballPlayer[capacity];
        }

        public int GetCount()
        {
            lock (m)
            {
                return count;
            }
        }

        public void AddItem(VolleyballPlayer player)
		{
			lock (m)
			{
				while (count == buffer.Length)
				{
					Monitor.Wait(m);
				}

				buffer[tail] = player;
				tail = (tail + 1) % buffer.Length;
				count++;

				Monitor.PulseAll(m);
			}
		}

		public VolleyballPlayer RemoveItem()
		{
			lock (m)
			{
				while (count == 0)
				{
					if (completed)
					{
						return null;
					}

					Monitor.Wait(m);
				}

				var item = buffer[head];
				head = (head + 1) % buffer.Length;
				count--;

				Monitor.PulseAll(m);
				return item;
			}
		}

		public void Complete()
		{
			lock (m)
			{
				completed = true;
				Monitor.PulseAll(m);
			}
		}
	}
}

