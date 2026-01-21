namespace L1a
{
	public class ResultMonitor
	{
        private readonly VolleyballPlayer[] buffer;
        private readonly object m = new object();
        private int count = 0;
        private readonly IComparer<VolleyballPlayer> comparer = new WinningAscendingComparer();

        private sealed class WinningAscendingComparer : IComparer<VolleyballPlayer>
        {
            public int Compare(VolleyballPlayer a, VolleyballPlayer b)
            {
                if (ReferenceEquals(a, b))
                {
                    return 0;
                }

                if (a is null)
                {
                    return -1;
                }

                if (b is null)
                {
                    return 1;
                }

                return a.Winning.CompareTo(b.Winning);
            }
        }

        public ResultMonitor(int capacity)
        {
            if (capacity <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(capacity));
            }

            buffer = new VolleyballPlayer[capacity];
        }

        public void AddItemSorted(VolleyballPlayer player)
        {
            lock (m)
            {
                if (count == buffer.Length)
                {
                    throw new InvalidOperationException("Result buffer is full");
                }

                int idx = Array.BinarySearch(buffer, 0, count, player, comparer);
                if (idx < 0)
                {
                    idx = ~idx;
                }

                if (idx < count)
                {
                    Array.Copy(buffer, idx, buffer, idx + 1, count - idx);
                }

                buffer[idx] = player;
                count++;
            }
        }

        public VolleyballPlayer[] GetItems()
        {
            var result = new VolleyballPlayer[count];

            Array.Copy(buffer, 0, result, 0, count);

            return result;
        }
    }
}

