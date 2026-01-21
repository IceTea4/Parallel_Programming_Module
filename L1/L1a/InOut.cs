using System.Runtime.Serialization.Json;
using System.Text;

namespace L1a
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
            write.WriteLine("Name                 |   Games |   Winning");
            write.WriteLine(new string('-', 50));

            int nr = 0;

            if (results != null)
            {
                foreach (var p in results)
                {
                    if (p == null)
                    {
                        continue;
                    }

                    write.WriteLine($"{nr++} {p.Name,-20} | {p.Games,7} | {p.Winning,8:0.##}");
                }
            }
        }

    }
}

