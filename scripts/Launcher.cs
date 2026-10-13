using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace IrisApp
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            try
            {
                string repoDir = @"C:\kirtan\IRIS";
                string packagedExe = Path.Combine(repoDir, @"desktop\dist\IRIS-win32-x64\IRIS.exe");

                if (File.Exists(packagedExe))
                {
                    ProcessStartInfo psi = new ProcessStartInfo
                    {
                        FileName = packagedExe,
                        WorkingDirectory = Path.Combine(repoDir, @"desktop\dist\IRIS-win32-x64"),
                        UseShellExecute = true
                    };
                    Process.Start(psi);
                    return;
                }

                string batFile = Path.Combine(repoDir, "start-iris-app.bat");
                if (File.Exists(batFile))
                {
                    ProcessStartInfo psi = new ProcessStartInfo
                    {
                        FileName = "cmd.exe",
                        Arguments = "/c \"" + batFile + "\"",
                        WorkingDirectory = repoDir,
                        WindowStyle = ProcessWindowStyle.Hidden,
                        CreateNoWindow = true
                    };
                    Process.Start(psi);
                    return;
                }

                MessageBox.Show(
                    "Could not find IRIS installation at " + repoDir + ".\nPlease ensure the folder exists.",
                    "IRIS Desktop",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Error launching IRIS:\n" + ex.Message,
                    "IRIS Desktop Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }
    }
}
