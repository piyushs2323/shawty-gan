import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { formatApiError } from "@/lib/api";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@himawari24.app");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back, admin");
      navigate("/");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-bg grain flex items-center justify-center min-h-screen px-4">
      <div className="w-full max-w-md fade-up">
        <div className="flex items-center gap-3 mb-8">
          <div className="h-11 w-11 rounded-xl bg-[#E50914] flex items-center justify-center shadow-lg shadow-red-900/40">
            <Play className="h-6 w-6 text-white fill-white" />
          </div>
          <div>
            <h1 className="font-display text-2xl font-extrabold tracking-tight text-white leading-none">
              himawari<span className="text-[#E50914]">24</span>
            </h1>
            <p className="text-xs text-slate-500 mt-1">Netflix Email Access · Admin</p>
          </div>
        </div>

        <div className="h24-card glass p-8">
          <div className="flex items-center gap-2 text-slate-300 mb-6">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-medium">Admin authentication</span>
          </div>
          <form onSubmit={submit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-slate-400 text-xs uppercase tracking-wide">
                Email
              </Label>
              <Input
                id="email"
                data-testid="login-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="bg-black/40 border-white/10 text-slate-100 h-11"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-400 text-xs uppercase tracking-wide">
                Password
              </Label>
              <Input
                id="password"
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-black/40 border-white/10 text-slate-100 h-11"
                placeholder="••••••••"
                required
              />
            </div>
            <Button
              type="submit"
              data-testid="admin-login-button"
              disabled={loading}
              className="w-full h-11 bg-[#E50914] hover:bg-[#c40810] text-white font-semibold rounded-xl"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
            </Button>
          </form>
          <p className="text-center text-sm text-slate-500 mt-6">
            Don't have an account?{" "}
            <Link to="/register" className="text-[#E50914] hover:underline font-medium">
              Create one
            </Link>
          </p>
        </div>
        <p className="text-center text-xs text-slate-600 mt-6">
          Read-only mailbox access · Encrypted tokens at rest
        </p>
      </div>
    </div>
  );
}

