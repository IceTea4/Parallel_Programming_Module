using System.Runtime.Serialization.Json;
using System.Text;

namespace L1b
{
	public static class InOut
	{
		public static PlayersWrapper Read(string path)
		{
            if (!File.Exists(path))
                throw new FileNotFoundException($"File not found: {path}");

            string json = File.ReadAllText(path, Encoding.UTF8);
            using (MemoryStream stream = new MemoryStream(Encoding.UTF8.GetBytes(json)))
            {
                var serializer = new DataContractJsonSerializer(typeof(PlayersWrapper));
                return (PlayersWrapper)serializer.ReadObject(stream);
            }
        }

        public static void Write(string path, List<VolleyballPlayer> starting, VolleyballPlayer[] results)
        {
            using var write = new StreamWriter(path, false, Encoding.UTF8);

            write.WriteLine("STARTING DATA");
            write.WriteLine("Name                 |   Games |   Winning");
            write.WriteLine(new string('-', 50));

            if (starting != null)
            {
                foreach (var p in starting)
                {
                    if (p == null)
                    {
                        continue;
                    }

                    write.WriteLine($"{p.Name,-20} | {p.Games,7} | {p.Winning,8:0.##}");
                }
            }

            write.WriteLine();

            write.WriteLine("RESULTS (filtered)");
            write.WriteLine("NR  | Name                 |   Games |   Winning |   Sum");
            write.WriteLine(new string('-', 60));

            int nr = 0;
            float sum = 0;
            int gameSum = 0;
            float winSum = 0;

            if (results != null)
            {
                foreach (var p in results)
                {
                    if (p == null)
                    {
                        continue;
                    }

                    sum += p.Games + p.Winning;
                    gameSum += p.Games;
                    winSum += p.Winning;

                    write.WriteLine($"{nr++,3} | {p.Name,-20} | {p.Games,7} | {p.Winning,8:0.##} | {p.Games + p.Winning,8:0.##}");
                }
            }

            write.WriteLine($"Bendra lauku suma          | {gameSum,7} | {winSum,8:0.##} | {sum,8:0.##}");
        }

    }
}

