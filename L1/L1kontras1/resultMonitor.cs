namespace L1kontras1
{
	public class resultMonitor
	{
		private readonly object m = new object();
		private int c = 9;
		private int d = 0;
		private int version = 0;
		private int reads = 0;
		private bool done = false;
		private int changes = 0;
		private readonly int maxChanges = 10;

		public bool IsDone()
		{
			lock (m) return done;
		}

		public void ChangeBy(int delta)
		{
			lock (m)
			{
				while (!done && reads < 2)
				{
					Monitor.Wait(m);
				}

				if (done)
				{
					return;
				}

				c += delta;
				d -= delta;
				version++;
				reads = 0;
				changes++;

				if (changes >= maxChanges)
				{
					done = true;
				}

				Monitor.PulseAll(m);
			}
		}

		public (int c, int d, int ver) ReadNext(ref int lastSeenVer)
		{
			lock (m)
			{
				while (!done && version == lastSeenVer)
				{
					Monitor.Wait(m);
				}

				if (done)
				{
					return (c, d, version);
				}

				reads++;
				lastSeenVer = version;

				Monitor.PulseAll(m);

				return (c, d, version);
			}
		}

		public (int c, int d, int ver) GetVersion()
		{
			lock (m) return (c, d, version);
        }
	}
}
